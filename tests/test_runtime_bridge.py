import unittest
from paypal.runtime_bridge import (
    resolve_runtime_mode,
    effective_browser_runtime,
    seed_browser_profile,
)
from paypal.protocol import build_protocol


class RuntimeBridgeTests(unittest.TestCase):
    def test_runtime_modes(self):
        self.assertEqual(resolve_runtime_mode("protocol"), "protocol")
        self.assertEqual(resolve_runtime_mode("headless"), "headless")
        self.assertEqual(resolve_runtime_mode("auto"), "auto")
        self.assertIn(effective_browser_runtime("protocol"), {"protocol"})
        self.assertIn(effective_browser_runtime("headless"), {"headless", "roxy"})

    def test_seed_profile_country_not_hard_br(self):
        jp = seed_browser_profile(build_protocol("JP"))
        us = seed_browser_profile(build_protocol("US"))
        self.assertEqual(jp["country"], "JP")
        self.assertEqual(jp["locale"], "ja_JP")
        self.assertEqual(us["country"], "US")
        self.assertNotEqual(jp["timezone"], us["timezone"])


if __name__ == "__main__":
    unittest.main()
