import unittest
from unittest.mock import patch

from paypal.proxy import ProxyEntry, resolve_outbound_proxy


class ResolveOutboundProxyTests(unittest.TestCase):
    def test_empty_proxy_direct_when_nothing_works(self):
        """No filled proxy + system fail + direct fail still returns empty direct note path via probe."""
        with patch("paypal.proxy.list_system_proxy_entries", return_value=[]), patch(
            "paypal.proxy.probe_direct_exit", return_value=("1.2.3.4", 12)
        ):
            entry, ip, ms, note = resolve_outbound_proxy(
                "",
                allow_system_fallback=True,
                allow_direct_fallback=True,
            )
        self.assertIsNone(entry)
        self.assertEqual(ip, "1.2.3.4")
        self.assertEqual(ms, 12)
        self.assertEqual(note, "direct")

    def test_no_system_probe_when_system_fallback_disabled(self):
        """allow_system_fallback=False skips local/system candidates."""
        with patch("paypal.proxy.list_system_proxy_entries") as mock_sys, patch(
            "paypal.proxy.probe_direct_exit", return_value=("", 0)
        ):
            entry, ip, ms, note = resolve_outbound_proxy(
                "",
                allow_system_fallback=False,
                allow_direct_fallback=True,
            )
        self.assertIsNone(entry)
        self.assertEqual(note, "direct")
        mock_sys.assert_not_called()

    def test_filled_proxy_raises_when_probe_fails(self):
        bad = ProxyEntry(host="127.0.0.1", port=1, scheme="http")
        with patch("paypal.proxy.list_system_proxy_entries", return_value=[]), patch(
            "paypal.proxy.probe_proxy_entry", side_effect=ValueError("boom")
        ), patch(
            "paypal.proxy.resolve_working_proxy_entry", side_effect=ValueError("boom")
        ), patch(
            "paypal.proxy.ProxyEntry.parse", return_value=bad
        ):
            with self.assertRaises(ValueError):
                resolve_outbound_proxy(
                    "http://127.0.0.1:1",
                    allow_system_fallback=True,
                    allow_direct_fallback=True,
                )


if __name__ == "__main__":
    unittest.main()
