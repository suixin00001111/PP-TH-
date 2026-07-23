import unittest
from paypal.protocol import build_protocol, format_billing_line1, format_billing_line2
from paypal.oaipy_data import generate_user, generate_address
from paypal.flow import PayPalFlow
from paypal.proxy import build_proxy_config


class ProtocolContextTests(unittest.TestCase):
    def test_not_literal_th_constants(self):
        th = build_protocol("TH")
        jp = build_protocol("JP")
        us = build_protocol("US")
        br = build_protocol("BR")
        self.assertEqual(th.lang, "th")
        self.assertEqual(jp.lang, "ja")
        self.assertEqual(jp.locale_x, "ja_JP")
        self.assertNotEqual(jp.locale_x, th.locale_x)
        self.assertEqual(us.country_x, "US")
        self.assertEqual(us.content_lang, "en")
        self.assertTrue(br.send_identity_document)
        self.assertFalse(jp.send_identity_document)

    def test_address_styles_differ(self):
        th = format_billing_line1("th", "Sukhumvit Road", "12")
        us = format_billing_line1("us", "Main Street", "12")
        self.assertEqual(th, "Sukhumvit Road, 12")
        self.assertEqual(us, "12 Main Street")
        self.assertEqual(format_billing_line2("us", "Downtown"), "")
        self.assertEqual(format_billing_line2("th", "Watthana"), "Watthana")

    def test_flow_binds_protocol(self):
        user = generate_user(phone="+819012345678", country="JP")
        addr = generate_address(country="JP")
        from paypal.oaipy_data import generate_card
        flow = PayPalFlow(
            "BA-TESTTOKEN00000000",
            user,
            generate_card(),
            addr,
            proxy_config=build_proxy_config(enabled=False),
        )
        try:
            self.assertEqual(flow.protocol.code, "JP")
            self.assertEqual(flow.lang, "ja")
            self.assertEqual(flow.protocol.locale_x, "ja_JP")
            self.assertNotEqual(flow.protocol.lang, "th")
        finally:
            flow.close()


if __name__ == "__main__":
    unittest.main()
