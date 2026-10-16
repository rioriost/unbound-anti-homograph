import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fetch_confusables", ROOT / "scripts/fetch_confusables.py"
)
FETCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FETCH)


class FetchTests(unittest.TestCase):
    def test_download_failure_is_not_hidden(self):
        with patch.object(FETCH.urllib.request, "urlopen", side_effect=OSError("offline")):
            with self.assertRaisesRegex(OSError, "offline"):
                FETCH.verified_data()

    def test_wrong_checksum_is_rejected_before_parsing(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"unexpected data"
        with patch.object(FETCH.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                FETCH.verified_data()


if __name__ == "__main__":
    unittest.main()
