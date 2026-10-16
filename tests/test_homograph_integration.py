import os
from pathlib import Path
import shutil
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
BINARY = os.environ.get("UNBOUND_BINARY")
UNPATCHED_BINARY = os.environ.get("UNBOUND_UNPATCHED_BINARY")
DATA = os.environ.get("UNBOUND_CONFUSABLES")
SCRIPT = Path(os.environ.get("UNBOUND_FILTER_SCRIPT", ROOT / "files/homograph_filter.py"))


class Upstream(socketserver.BaseRequestHandler):
    def handle(self):
        packet, connection = self.request
        self.server.queries += 1
        offset = 12
        while packet[offset]:
            offset += packet[offset] + 1
        end = offset + 5
        qtype = struct.unpack("!H", packet[offset + 1:offset + 3])[0]
        address = {1: b"\xc0\x00\x02\x7b", 28: socket.inet_pton(socket.AF_INET6, "2001:db8::123")}
        answer = b""
        if qtype in address:
            value = address[qtype]
            answer = b"\xc0\x0c" + struct.pack("!HHIH", qtype, 1, 300, len(value)) + value
        header = packet[:2] + struct.pack("!HHHHH", 0x8580, 1, bool(answer), 0, 0)
        connection.sendto(header + packet[12:end] + answer, self.client_address)


@unittest.skipUnless(BINARY, "Set UNBOUND_BINARY for real startup tests")
class ResolverStartupFailureTests(unittest.TestCase):
    def assert_startup_rejected(self, binary_name, data, expected_message):
        binary = shutil.which(binary_name)
        self.assertIsNotNone(binary, "UNBOUND_BINARY executable was not found")
        with tempfile.TemporaryDirectory(prefix="ub-homograph-startup-") as directory:
            directory = Path(directory)
            script = directory / "homograph_filter.py"
            shutil.copyfile(SCRIPT, script)
            if data is not None:
                (directory / "confusables.txt").write_bytes(data)
            with socket.socket() as port_probe:
                port_probe.bind(("127.0.0.1", 0))
                port = port_probe.getsockname()[1]
            config = directory / "unbound.conf"
            config.write_text(
                'server:\n'
                '  interface: 127.0.0.1\n'
                '  port: {port}\n'
                '  username: ""\n'
                '  chroot: ""\n'
                '  directory: "{directory}"\n'
                '  pidfile: ""\n'
                '  use-syslog: no\n'
                '  do-ip6: no\n'
                '  module-config: "python iterator"\n'
                'python:\n'
                '  python-script: "{script}"\n'.format(
                    port=port, directory=directory, script=script,
                ),
                encoding="utf-8",
            )
            environment = os.environ.copy()
            module_path = Path(binary).parent / "pythonmod"
            if (module_path / "unboundmodule.py").is_file():
                environment["PYTHONPATH"] = str(module_path)
            result = subprocess.run(
                [binary, "-d", "-c", str(config)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, timeout=10, check=False, env=environment,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn(expected_message, result.stdout)

    def test_missing_or_bad_data_aborts_startup(self):
        for data in (None, b"", b"bad\n", b"\xff"):
            with self.subTest(data=data):
                self.assert_startup_rejected(BINARY, data, "homograph: cannot load ")

    @unittest.skipUnless(UNPATCHED_BINARY and DATA, "Set UNBOUND_UNPATCHED_BINARY and UNBOUND_CONFUSABLES")
    def test_unpatched_binary_aborts_startup(self):
        self.assert_startup_rejected(
            UNPATCHED_BINARY, Path(DATA).read_bytes(),
            "homograph: Unbound lacks the required inplace-reply-veto patch",
        )


@unittest.skipUnless(BINARY and DATA, "Set UNBOUND_BINARY and UNBOUND_CONFUSABLES for real DNS tests")
class ResolverIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.binary = shutil.which(BINARY)
        self.assertIsNotNone(self.binary, "UNBOUND_BINARY executable was not found")
        self.control_binary = Path(self.binary).with_name("unbound-control")
        self.assertTrue(self.control_binary.is_file(), "unbound-control was not found next to Unbound")

    def query(self, name, qtype=1, tcp=False):
        labels = name.rstrip(".").encode("ascii").split(b".")
        question = b"".join(bytes([len(label)]) + label for label in labels) + b"\0"
        packet = struct.pack("!HHHHHH", 12345, 0x0100, 1, 0, 0, 0)
        packet += question + struct.pack("!HH", qtype, 1)
        kind = socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM
        with socket.socket(socket.AF_INET, kind) as client:
            client.settimeout(2)
            client.connect(("127.0.0.1", self.port))
            if tcp:
                client.sendall(struct.pack("!H", len(packet)) + packet)
                data = bytearray()
                while len(data) < 2:
                    chunk = client.recv(2 - len(data))
                    if not chunk:
                        raise EOFError("DNS TCP connection closed before length")
                    data.extend(chunk)
                length = struct.unpack("!H", data)[0]
                data = bytearray()
                while len(data) < length:
                    chunk = client.recv(length - len(data))
                    if not chunk:
                        raise EOFError("DNS TCP connection closed")
                    data.extend(chunk)
            else:
                client.send(packet)
                data = client.recv(4096)
        flags, _, answers = struct.unpack("!HHH", data[2:8])
        return flags & 15, answers

    def start_resolver(self, filtered):
        module_config = "python iterator" if filtered else "iterator"
        python = '\npython:\n  python-script: "{}"\n'.format(self.script) if filtered else ""
        self.config.write_text(
            'server:\n'
            '  interface: 127.0.0.1\n'
            '  port: {port}\n'
            '  username: ""\n'
            '  chroot: ""\n'
            '  directory: "{directory}"\n'
            '  pidfile: ""\n'
            '  use-syslog: no\n'
            '  do-ip6: no\n'
            '  num-threads: 2\n'
            '  do-not-query-localhost: no\n'
            '  qname-minimisation: no\n'
            '  module-config: "{modules}"\n'
            '  local-zone: "local.example." static\n'
            '  local-data: "health.local.example. 300 IN A 192.0.2.1"\n'
            '  local-data: "xn--mazon-3ve.local.example. 300 IN A 192.0.2.2"\n'
            'remote-control:\n'
            '  control-enable: yes\n'
            '  control-use-cert: no\n'
            '  control-interface: "{control}"\n'
            'forward-zone:\n'
            '  name: "."\n'
            '  forward-addr: 127.0.0.1@{upstream}\n'
            '{python}'.format(
                port=self.port, directory=self.directory, modules=module_config,
                control=self.directory / "control.sock",
                upstream=self.upstream.server_address[1], python=python,
            ),
            encoding="utf-8",
        )
        self.log = self.log_path.open("ab")
        self.process = subprocess.Popen(
            [self.binary, "-d", "-c", str(self.config)],
            stdout=self.log, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and self.process.poll() is None:
            try:
                if self.query("health.local.example") == (0, 1):
                    return
            except (ConnectionRefusedError, socket.timeout):
                pass
            time.sleep(0.05)
        self.fail("Unbound failed to start:\n" + self.log_path.read_text())

    def stop_resolver(self):
        if self.process is not None:
            self.process.terminate()
            self.process.wait(timeout=10)
            self.process = None
        if self.log is not None:
            self.log.close()
            self.log = None

    def control(self, command, data=None):
        return subprocess.run(
            [str(self.control_binary), "-c", str(self.config), command],
            input=data, text=True, capture_output=True, check=True,
        ).stdout

    def test_real_uncached_cached_and_local_answers(self):
        self.process = None
        self.log = None
        with tempfile.TemporaryDirectory(prefix="ub-homograph-") as directory:
            self.directory = Path(directory)
            self.config = self.directory / "unbound.conf"
            self.log_path = self.directory / "unbound.log"
            self.script = self.directory / "homograph_filter.py"
            shutil.copyfile(SCRIPT, self.script)
            shutil.copyfile(DATA, self.directory / "confusables.txt")
            with socket.socket() as port_probe:
                port_probe.bind(("127.0.0.1", 0))
                self.port = port_probe.getsockname()[1]
            with socketserver.UDPServer(("127.0.0.1", 0), Upstream) as self.upstream:
                self.upstream.queries = 0
                thread = threading.Thread(target=self.upstream.serve_forever, daemon=True)
                thread.start()
                try:
                    self.start_resolver(filtered=False)
                    cached_name = "xn--mazon-3ve.cached.example"
                    self.assertEqual(self.query(cached_name), (0, 1))
                    cache = self.control("dump_cache")
                    self.assertIn(cached_name, cache)
                    self.stop_resolver()

                    self.start_resolver(filtered=True)
                    self.control("load_cache", cache)
                    calls = self.upstream.queries
                    self.assertEqual(
                        self.query(cached_name), (5, 0), self.log_path.read_text()
                    )
                    self.assertEqual(self.upstream.queries, calls)
                    for tcp in (False, True):
                        for qtype in (1, 28, 64, 65, 15, 16, 255):
                            with self.subTest(tcp=tcp, qtype=qtype):
                                self.assertEqual(
                                    self.query("XN--MAZON-3VE.remote.example", qtype, tcp),
                                    (5, 0),
                                )
                    self.assertEqual(
                        self.query("xn--mazon-3ve.local.example"), (2, 0)
                    )
                    for label in ("amazon", "b\u00fccher", "\u65e5\u672c\u8a9e"):
                        name = label.encode("idna").decode("ascii") + ".remote.example"
                        with self.subTest(allowed=name):
                            self.assertEqual(self.query(name), (0, 1))
                    self.assertEqual(self.query("xn--.remote.example"), (5, 0))
                    self.assertIn("homograph: loaded ", self.log_path.read_text())
                finally:
                    self.stop_resolver()
                    self.upstream.shutdown()
                    thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
