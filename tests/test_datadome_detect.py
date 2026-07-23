import unittest
from paypal.flow import PayPalFlow


class DataDomeDetectTests(unittest.TestCase):
    def test_403_is_block(self):
        self.assertTrue(PayPalFlow._looks_like_hard_datadome_block(403, "<html></html>"))

    def test_normal_paypal_page_with_datadome_script_not_block(self):
        html = "<html><script src=\"https://example.com/datadome.js\"></script><body>PayPal</body></html>"
        self.assertFalse(PayPalFlow._looks_like_hard_datadome_block(200, html))

    def test_captcha_delivery_is_block(self):
        html = "<html>captcha-delivery.com challenge</html>"
        self.assertTrue(PayPalFlow._looks_like_hard_datadome_block(200, html))


if __name__ == "__main__":
    unittest.main()
