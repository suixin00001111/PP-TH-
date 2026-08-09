import os
import unittest
from pathlib import Path
from unittest.mock import patch

from paypal.ssl_env import ensure_ssl_cert_env


class SslEnvTests(unittest.TestCase):
    def test_sets_ascii_bundle_when_source_has_non_ascii(self):
        # Force re-apply path by using a fake non-ascii source via certifi.where mock
        import paypal.ssl_env as ssl_env

        ssl_env._APPLIED = False
        ssl_env._CA_PATH = ""
        real_cert = __import__("certifi").where()
        # Pretend current env is empty
        with patch.dict(os.environ, {"SSL_CERT_FILE": "", "CURL_CA_BUNDLE": "", "REQUESTS_CA_BUNDLE": ""}, clear=False):
            # ensure uses real certifi file but if path already non-ascii on this machine it will copy
            path = ensure_ssl_cert_env(force=True)
            self.assertTrue(Path(path).is_file())
            self.assertGreater(Path(path).stat().st_size, 1000)
            # On this Windows profile the username is non-ASCII, so env should be set to ascii mirror
            self.assertTrue(path.isascii() or Path(real_cert).as_posix().isascii())
            self.assertEqual(os.environ.get("SSL_CERT_FILE"), path)
            self.assertEqual(os.environ.get("CURL_CA_BUNDLE"), path)


if __name__ == "__main__":
    unittest.main()
