import unittest
from paypal.session import looks_like_paypal_authchallenge, PayPalAuthChallenge


class AuthChallengeTests(unittest.TestCase):
    def test_detect_html(self):
        self.assertTrue(looks_like_paypal_authchallenge("<html>authchallenge captcha</html>"))
        self.assertFalse(looks_like_paypal_authchallenge('{"data":{}}'))
        self.assertFalse(looks_like_paypal_authchallenge(""))

    def test_exception_fields(self):
        e = PayPalAuthChallenge("SignUp", 200, "dbg", "<html/>")
        self.assertEqual(e.operation_name, "SignUp")
        self.assertIn("authchallenge", str(e).lower())


if __name__ == "__main__":
    unittest.main()
