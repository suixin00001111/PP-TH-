import unittest

from paypal.oaipy_data import generate_user, generate_address, generate_card, normalize_thailand_phone
from web import normalize_thailand_phone as web_norm


class ThailandProfileTests(unittest.TestCase):
    def test_phone_e164(self):
        self.assertEqual(web_norm("+66812345678"), "+66812345678")
        self.assertEqual(web_norm("0812345678"), "+66812345678")
        self.assertEqual(web_norm("66812345678"), "+66812345678")

    def test_phone_reject_br(self):
        with self.assertRaises(ValueError):
            web_norm("+5511987654321")

    def test_generate_user_th(self):
        user = generate_user("+66812345678")
        self.assertEqual(user.phone_country_code, "+66")
        self.assertEqual(user.phone, "+66812345678")
        self.assertTrue(user.phone_local.startswith(("6", "8", "9")))
        self.assertEqual(len(user.phone_local), 9)

    def test_generate_address_th(self):
        addr = generate_address()
        self.assertEqual(addr.country, "TH")
        self.assertTrue(addr.postal_code.isdigit())
        self.assertGreaterEqual(len(addr.postal_code), 5)

    def test_generate_card_luhn_len(self):
        card = generate_card()
        self.assertEqual(len(card.number), 16)
        self.assertIn("/", card.expiry)


if __name__ == "__main__":
    unittest.main()
