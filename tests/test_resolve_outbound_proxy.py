import unittest
from unittest.mock import patch

from paypal.proxy import ProxyEntry, resolve_outbound_proxy


class ResolveOutboundProxyTests(unittest.TestCase):
    def test_require_proxy_false_returns_direct_when_nothing_works(self):
        with patch("paypal.proxy.get_system_proxy_entry", return_value=None):
            entry, ip, ms, note = resolve_outbound_proxy("", require_proxy=False, allow_system_fallback=True)
        self.assertIsNone(entry)
        self.assertEqual(ip, "")
        self.assertTrue(str(note).startswith("direct"))

    def test_no_proxy_skips_system_probe_when_system_assist_disabled(self):
        """Default: no filled proxy + require_proxy=False + USE_SYSTEM_PROXY=0 → instant direct."""
        with patch.dict("os.environ", {"PAYPAL_USE_SYSTEM_PROXY": "0"}, clear=False), patch(
            "paypal.proxy._CFG_USE_SYSTEM_PROXY", False
        ), patch("paypal.proxy.get_system_proxy_entry") as mock_sys:
            entry, ip, ms, note = resolve_outbound_proxy(
                "", require_proxy=False, allow_system_fallback=True
            )
        self.assertIsNone(entry)
        self.assertEqual(note, "direct")
        mock_sys.assert_not_called()

    def test_filled_proxy_still_required(self):
        bad = ProxyEntry(host="127.0.0.1", port=1, scheme="http")
        with patch("paypal.proxy.get_system_proxy_entry", return_value=None), patch(
            "paypal.proxy.probe_proxy_entry", side_effect=ValueError("boom")
        ), patch(
            "paypal.proxy.resolve_working_proxy_entry", side_effect=ValueError("boom")
        ), patch(
            "paypal.proxy.ProxyEntry.parse", return_value=bad
        ):
            with self.assertRaises(ValueError):
                resolve_outbound_proxy("http://127.0.0.1:1", require_proxy=True)


if __name__ == "__main__":
    unittest.main()
