import unittest
from unittest.mock import patch

from paypal.proxy import (
    ProxyConfig,
    ProxyEntry,
    parse_proxy_candidates,
    resolve_outbound_proxy,
    split_proxy_inputs,
)


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

    def test_split_proxy_inputs_multi_separators(self):
        lines = split_proxy_inputs(
            raw="http://a:1@h:1\nhttp://b:2@h:2;http://c:3@h:3|http://d:4@h:4\n# comment\nhttp://a:1@h:1"
        )
        self.assertEqual(
            lines,
            [
                "http://a:1@h:1",
                "http://b:2@h:2",
                "http://c:3@h:3",
                "http://d:4@h:4",
            ],
        )

    def test_split_proxy_inputs_keeps_comma_in_password(self):
        # Comma must NOT split (passwords / provider strings may contain it).
        lines = split_proxy_inputs(raw="user:p,ass@host:8080")
        self.assertEqual(lines, ["user:p,ass@host:8080"])

    def test_parse_proxy_candidates_skips_bad_lines(self):
        entries, notes = parse_proxy_candidates(
            raw="http://u:p@good.host:3010\nnot-a-proxy\nhttp://u2:p2@good2.host:3011"
        )
        self.assertEqual(len(entries), 2)
        self.assertTrue(any("parse#" in n for n in notes))

    def test_random_selection_picks_one_line_only(self):
        """Job pool contract: random pick exactly one line; no multi-line failover."""
        first = ProxyEntry(host="a.example", port=1, scheme="http", username="u", password="p")
        second = ProxyEntry(host="b.example", port=2, scheme="http", username="u", password="p")
        probed: list[str] = []

        def fake_resolve(entry, timeout=12.0):
            probed.append(entry.host)
            return entry, "9.9.9.9", 11

        with patch("paypal.proxy.list_system_proxy_entries", return_value=[]), patch(
            "paypal.proxy.resolve_working_proxy_entry", side_effect=fake_resolve
        ), patch(
            "paypal.proxy.parse_proxy_candidates",
            return_value=([first, second], []),
        ), patch(
            "paypal.proxy.split_proxy_inputs",
            return_value=["http://u:p@a.example:1", "http://u:p@b.example:2"],
        ), patch(
            "paypal.proxy.random.choice",
            return_value=second,
        ):
            entry, ip, ms, note = resolve_outbound_proxy(
                "pool",
                allow_system_fallback=False,
                allow_direct_fallback=False,
                filled_selection="random",
            )
        self.assertEqual(entry.host, "b.example")
        self.assertEqual(probed, ["b.example"])
        self.assertEqual(note, "filled")

    def test_sequential_keeps_input_order(self):
        first = ProxyEntry(host="a.example", port=1, scheme="http", username="u", password="p")
        second = ProxyEntry(host="b.example", port=2, scheme="http", username="u", password="p")
        order: list[str] = []

        def fake_resolve(entry, timeout=12.0):
            order.append(entry.host)
            return entry, "1.1.1.1", 5

        with patch("paypal.proxy.list_system_proxy_entries", return_value=[]), patch(
            "paypal.proxy.resolve_working_proxy_entry", side_effect=fake_resolve
        ), patch(
            "paypal.proxy.parse_proxy_candidates",
            return_value=([first, second], []),
        ), patch(
            "paypal.proxy.split_proxy_inputs",
            return_value=["http://u:p@a.example:1", "http://u:p@b.example:2"],
        ):
            entry, ip, ms, note = resolve_outbound_proxy(
                "pool",
                allow_system_fallback=False,
                allow_direct_fallback=False,
                filled_selection="sequential",
            )
        self.assertEqual(entry.host, "a.example")
        self.assertEqual(order[0], "a.example")

    def test_filled_does_not_use_system_when_fallback_off(self):
        """Web/job contract: filled pool fails => no silent Clash 7897 success."""
        bad = ProxyEntry(host="bad.proxy", port=9, scheme="http", username="u", password="p")
        system = ProxyEntry(host="127.0.0.1", port=7897, scheme="http")
        with patch(
            "paypal.proxy.list_system_proxy_entries", return_value=[system]
        ) as mock_sys, patch(
            "paypal.proxy.resolve_working_proxy_entry", side_effect=ValueError("denied")
        ), patch(
            "paypal.proxy.probe_proxy_entry", side_effect=ValueError("denied")
        ), patch(
            "paypal.proxy.parse_proxy_candidates", return_value=([bad], [])
        ), patch(
            "paypal.proxy.split_proxy_inputs", return_value=["http://u:p@bad.proxy:9"]
        ), patch(
            "paypal.proxy.probe_direct_exit", return_value=("8.8.8.8", 5)
        ) as mock_direct:
            with self.assertRaises(ValueError) as ctx:
                resolve_outbound_proxy(
                    "http://u:p@bad.proxy:9",
                    allow_system_fallback=False,
                    allow_direct_fallback=False,
                )
        self.assertIn("填写", str(ctx.exception))
        mock_sys.assert_not_called()
        mock_direct.assert_not_called()

    def test_proxy_config_label_hides_endpoint(self):
        entry = ProxyEntry(host="secret.example", port=3010, scheme="socks5h", username="u", password="p")
        cfg = ProxyConfig(enabled=True, entry=entry, resolved_from="filled")
        self.assertEqual(cfg.label, "代理开")
        self.assertNotIn("secret", cfg.label)
        self.assertNotIn("u", cfg.label)
        off = ProxyConfig(enabled=False, entry=None, resolved_from="direct")
        self.assertEqual(off.label, "直连")

    def test_filter_pool_keeps_matching_country_drops_mismatch(self):
        from paypal.proxy import filter_filled_proxy_pool

        good = ProxyEntry(host="good.example", port=1, username="u", password="p", scheme="http")
        bad = ProxyEntry(host="bad.example", port=2, username="u", password="p", scheme="http")
        dead = ProxyEntry(host="dead.example", port=3, username="u", password="p", scheme="http")

        def fake_resolve(entry, timeout=12.0):
            if entry.host == "good.example":
                return entry, "1.1.1.1", 10
            if entry.host == "bad.example":
                return entry, "2.2.2.2", 11
            raise ValueError("unreachable")

        def fake_geo(ip, timeout=8.0, via_proxy_url=None):
            return {"1.1.1.1": "JP", "2.2.2.2": "US"}.get(ip, "")

        raw = "\n".join(
            [
                "http://u:p@good.example:1",
                "http://u:p@bad.example:2",
                "http://u:p@dead.example:3",
            ]
        )
        with patch("paypal.proxy.resolve_working_proxy_entry", side_effect=fake_resolve), patch(
            "paypal.proxy.lookup_ip_country", side_effect=fake_geo
        ):
            result = filter_filled_proxy_pool(raw, expected_country="JP", timeout=5.0)

        self.assertTrue(result["ok"])
        self.assertEqual(result["kept_count"], 1)
        self.assertEqual(result["removed_count"], 2)
        self.assertEqual(result["country_mismatch_count"], 1)
        self.assertEqual(result["unreachable_count"], 1)
        self.assertEqual(result["kept_proxies"], ["http://u:p@good.example:1"])
        self.assertEqual(result["exit_country"], "JP")
        self.assertIn("JP", result["message"])

    def test_filter_pool_all_mismatch_clears(self):
        from paypal.proxy import filter_filled_proxy_pool

        entry = ProxyEntry(host="x.example", port=9, username="u", password="p", scheme="http")

        with patch(
            "paypal.proxy.resolve_working_proxy_entry",
            return_value=(entry, "9.9.9.9", 5),
        ), patch("paypal.proxy.lookup_ip_country", return_value="BR"):
            result = filter_filled_proxy_pool(
                "http://u:p@x.example:9",
                expected_country="TH",
                timeout=5.0,
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["kept_proxies"], [])
        self.assertEqual(result["country_mismatch_count"], 1)
        self.assertIn("无可用", result["message"])


if __name__ == "__main__":
    unittest.main()
