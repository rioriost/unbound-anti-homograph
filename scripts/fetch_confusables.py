#!/usr/bin/env python3
"""Download and verify the policy's pinned Unicode data, without activating it."""

import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import urllib.request


URL = (
    "https://raw.githubusercontent.com/unicode-org/unicodetools/"
    "48afe632bf194a20bcd27c3488b49dc23274b684/"
    "unicodetools/data/security/17.0.0/confusables.txt"
)
SHA256 = "091c7f82fc39ef208faf8f94d29c244de99254675e09de163160c810d13ef22a"
ROOT = Path(__file__).resolve().parents[1]


def verified_data():
    with urllib.request.urlopen(URL, timeout=60) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != SHA256:
        raise ValueError("Unicode data SHA-256 mismatch: " + digest)
    spec = importlib.util.spec_from_file_location(
        "homograph_filter", ROOT / "files/homograph_filter.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    mappings = module.parse_confusables(data.decode("utf-8").splitlines())
    if len(mappings) != 1407:
        raise ValueError("Unexpected Unicode 17.0.0 mapping count: " + str(len(mappings)))
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", nargs="?", type=Path, default=ROOT / "files/confusables.txt")
    destination = parser.parse_args().destination
    data = verified_data()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
            os.fchmod(output.fileno(), 0o644)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink()
    print("Verified Unicode 17.0.0: 1407 mappings; " + str(destination))


if __name__ == "__main__":
    main()
