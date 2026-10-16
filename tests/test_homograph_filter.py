import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
DATA = """\
# Representative and synthetic mappings for deterministic policy tests.
0430 ; 0061 ; MA # Cyrillic a
03BF ; 006F ; MA # Greek omicron
0131 ; 0069 ; MA # Latin dotless i
3007 ; 004F ; MA # Ideographic zero
11700 ; 0072 006E ; MA # Multiple ASCII letters
00FC ; 0075 0308 ; MA # Accented targets are not ASCII-letter sequences
03B1 ; 0061 ; MA
0071 ; 0071 ; MA # ASCII sources must not be blocked
0660 ; 002E ; MA # Punctuation targets must not be blocked
"""


def wire_name(*labels):
    return b"".join(bytes([len(label)]) + label for label in labels) + b"\0"


def ace(label):
    return b"xn--" + label.encode("punycode")


def load_filter():
    spec = importlib.util.spec_from_file_location(
        "homograph_filter", ROOT / "files/homograph_filter.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ASCII_CONFUSABLES = module.parse_confusables(DATA.splitlines())
    for index, name in enumerate((
        "MODULE_EVENT_NEW", "MODULE_EVENT_PASS", "MODULE_EVENT_MODDONE",
        "MODULE_WAIT_MODULE", "MODULE_FINISHED", "MODULE_ERROR",
    )):
        setattr(module, name, index)
    module.RCODE_NOERROR = 0
    module.RCODE_REFUSED = 5
    module.INPLACE_REPLY_VETO_SUPPORTED = 1
    module.log_info = Mock()
    module.log_err = Mock()
    return module


class LabelPolicyTests(unittest.TestCase):
    def setUp(self):
        self.module = load_filter()

    def check(self, *labels):
        return self.module.block_reason(
            wire_name(*labels), self.module.ASCII_CONFUSABLES
        )

    def test_confusable_non_ascii_letters_are_rejected(self):
        for label in ("\u0430mazon", "\u03bf", "\u0131", "\u3007", "\U00011700"):
            with self.subTest(label=label):
                self.assertIsNotNone(self.check(ace(label), b"com"))

    def test_single_script_labels_are_rejected_too(self):
        self.assertIsNotNone(self.check(ace("\u0430\u0430\u0430"), b"com"))

    def test_every_label_including_subdomains_and_tlds_is_checked(self):
        bad = ace("\u0430")
        for labels in ((bad, b"example", b"com"),
                       (b"www", bad, b"com"), (b"example", bad)):
            with self.subTest(labels=labels):
                self.assertIsNotNone(self.check(*labels))

    def test_ascii_and_unrelated_idns_are_allowed(self):
        for labels in (
            (b"amazon", b"com"),
            (b"rnazon", b"com"),
            (b"prefix-xn--", b"com"),
            (b"_https", b"_tcp", b"example", b"com"),
            (ace("b\u00fccher"), b"de"),
            (ace("\u65e5\u672c\u8a9e"), b"jp"),
        ):
            with self.subTest(labels=labels):
                self.assertIsNone(self.check(*labels))
        self.assertIsNone(self.check())

    def test_case_insensitive_ace_prefix_and_payload(self):
        self.assertIsNotNone(self.check(b"XN--MAZON-3VE", b"COM"))

    def test_malformed_punycode_is_rejected(self):
        for label in (b"xn--", b"xn--abc-", b"xn--!", b"xn--99999999999999999999"):
            with self.subTest(label=label):
                self.assertIn("Punycode", self.check(label, b"com"))

    def test_wire_label_boundaries_cannot_be_changed_by_escaped_dots(self):
        self.assertIsNone(self.check(b"safe.xn--mazon-3ve", b"com"))
        self.assertIsNotNone(self.check(b"safe.with.dot", ace("\u0430"), b"com"))

    def test_invalid_wire_names_are_rejected(self):
        for name in (b"", b"\x03ab", b"\xc0\x0c", b"\0extra"):
            with self.subTest(name=name):
                self.assertIsNotNone(
                    self.module.block_reason(name, self.module.ASCII_CONFUSABLES)
                )

    def test_non_letter_targets_and_ascii_sources_are_excluded(self):
        mappings = self.module.ASCII_CONFUSABLES
        self.assertNotIn("q", mappings)
        self.assertNotIn("\u0660", mappings)
        self.assertNotIn("\u00fc", mappings)
        self.assertEqual(mappings["\U00011700"], "rn")

    def test_empty_or_invalid_data_does_not_silently_disable_filtering(self):
        for lines in ([], ["# comment"], ["bad"], ["0430;0061;XX"],
                      ["110000;0061;MA"], ["0430;;MA"]):
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                self.module.parse_confusables(lines)


class ModuleHookTests(unittest.TestCase):
    def setUp(self):
        self.module = load_filter()
        self.bad = SimpleNamespace(
            qname=wire_name(b"xn--mazon-3ve", b"com"),
            qname_str="xn--mazon-3ve.com.",
        )
        self.good = SimpleNamespace(
            qname=wire_name(b"amazon", b"com"), qname_str="amazon.com."
        )

    def state(self, qinfo):
        return SimpleNamespace(
            qinfo=qinfo, ext_state={}, return_msg=object(),
            return_rcode=0, no_cache_store=0,
        )

    def test_all_query_types_are_refused_without_positive_data(self):
        for event in (self.module.MODULE_EVENT_NEW, self.module.MODULE_EVENT_PASS):
            for qtype in (1, 28, 64, 65, 15, 16, 255):
                with self.subTest(event=event, qtype=qtype):
                    self.bad.qtype = qtype
                    state = self.state(self.bad)
                    self.assertTrue(self.module.operate(0, event, state, None))
                    self.assertEqual(state.return_rcode, 5)
                    self.assertIsNone(state.return_msg)
                    self.assertEqual(state.no_cache_store, 1)
                    self.assertEqual(state.ext_state[0], self.module.MODULE_FINISHED)
        self.module.log_info.assert_called()

    def test_allowed_queries_continue_to_existing_modules(self):
        state = self.state(self.good)
        self.module.operate(0, self.module.MODULE_EVENT_NEW, state, None)
        self.assertEqual(state.ext_state[0], self.module.MODULE_WAIT_MODULE)
        self.module.operate(0, self.module.MODULE_EVENT_MODDONE, state, None)
        self.assertEqual(state.ext_state[0], self.module.MODULE_FINISHED)
        self.module.log_info.assert_not_called()

    def test_positive_reply_callbacks_reject_cached_local_and_resolved_answers(self):
        self.assertFalse(self.module.inplace_reply(
            self.bad, None, object(), 0, None, None, None
        ))
        self.assertTrue(self.module.inplace_reply(
            self.good, None, object(), 0, None, None, None, future_argument=True
        ))

    def test_existing_errors_and_non_query_callbacks_are_unchanged(self):
        for rcode in (1, 2, 3, 5):
            self.assertTrue(self.module.inplace_reply(
                self.bad, None, None, rcode, None, None, None
            ))
        self.assertTrue(self.module.inplace_reply(
            None, None, None, 0, None, None, None
        ))

    def test_startup_loads_data_and_registers_all_bypass_hooks(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            Path(directory, "confusables.txt").write_text(DATA, encoding="utf-8")
            self.module.mod_env = {"script": str(Path(directory, "homograph_filter.py"))}
            for name in ("register_inplace_cb_reply", "register_inplace_cb_reply_cache",
                         "register_inplace_cb_reply_local"):
                setattr(self.module, name, Mock(return_value=True))
            env = object()
            self.assertTrue(self.module.init_standard(0, env))
            for name in ("register_inplace_cb_reply", "register_inplace_cb_reply_cache",
                         "register_inplace_cb_reply_local"):
                getattr(self.module, name).assert_called_once_with(
                    self.module.inplace_reply, env, 0
                )
            self.module.log_err.assert_not_called()
            self.module.log_info.assert_called_once_with(
                "homograph: loaded {} ASCII-letter confusables".format(
                    len(self.module.parse_confusables(DATA.splitlines()))
                )
            )

    def test_missing_data_raises_instead_of_returning_false(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            self.module.mod_env = {"script": str(Path(directory, "homograph_filter.py"))}
            with self.assertRaisesRegex(RuntimeError, "cannot load") as error:
                self.module.init_standard(0, object())
            self.module.log_err.assert_called_once_with(str(error.exception))
            self.assertIsInstance(error.exception.__cause__, FileNotFoundError)

    def test_bad_data_raises_instead_of_returning_false(self):
        for data in (b"", b"# comment only\n", b"bad\n", b"0430;0061;XX\n",
                     b"00FC;0075 0308;MA\n", b"\xff"):
            with self.subTest(data=data), tempfile.TemporaryDirectory(
                dir=ROOT / "tests"
            ) as directory:
                Path(directory, "confusables.txt").write_bytes(data)
                self.module.mod_env = {"script": str(Path(directory, "homograph_filter.py"))}
                self.module.log_err.reset_mock()
                with self.assertRaisesRegex(RuntimeError, "cannot load") as error:
                    self.module.init_standard(0, object())
                self.module.log_err.assert_called_once_with(str(error.exception))
                self.assertIsInstance(error.exception.__cause__, ValueError)

    def test_missing_patch_marker_raises_instead_of_returning_false(self):
        for marker in (None, False, 0):
            with self.subTest(marker=marker):
                if marker is None:
                    del self.module.INPLACE_REPLY_VETO_SUPPORTED
                else:
                    self.module.INPLACE_REPLY_VETO_SUPPORTED = marker
                self.module.log_err.reset_mock()
                with self.assertRaisesRegex(RuntimeError, "lacks the required") as error:
                    self.module.init_standard(0, object())
                self.module.log_err.assert_called_once_with(str(error.exception))

    def test_each_callback_registration_failure_raises_instead_of_returning_false(self):
        hooks = ("reply", "cache", "local")
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            Path(directory, "confusables.txt").write_text(DATA, encoding="utf-8")
            self.module.mod_env = {"script": str(Path(directory, "homograph_filter.py"))}
            for failed in hooks:
                with self.subTest(hook=failed):
                    registrations = [
                        Mock(return_value=hook != failed) for hook in hooks
                    ]
                    for name, register in zip((
                        "register_inplace_cb_reply", "register_inplace_cb_reply_cache",
                        "register_inplace_cb_reply_local",
                    ), registrations):
                        setattr(self.module, name, register)
                    self.module.log_err.reset_mock()
                    env = object()
                    with self.assertRaisesRegex(
                        RuntimeError, "cannot register {} callback".format(failed)
                    ) as error:
                        self.module.init_standard(0, env)
                    self.module.log_err.assert_called_once_with(str(error.exception))
                    for index, register in enumerate(registrations):
                        if index <= hooks.index(failed):
                            register.assert_called_once_with(self.module.inplace_reply, env, 0)
                        else:
                            register.assert_not_called()

    def test_unknown_events_are_errors_not_successful_fallbacks(self):
        state = self.state(self.good)
        self.module.operate(0, 999, state, None)
        self.assertEqual(state.ext_state[0], self.module.MODULE_ERROR)
        self.module.log_err.assert_called_once()


if __name__ == "__main__":
    unittest.main()
