import unittest
from paypal.oaipy_data import generate_user, generate_address, normalize_thailand_phone
from paypal.regions import normalize_phone, get_region


class JapanProfileTests(unittest.TestCase):
    def test_generate_user_jp(self):
        user = generate_user(phone="+819012345678", country="JP")
        self.assertTrue(user.phone.startswith("+81"))
        self.assertEqual(user.phone_country_code, "+81")
        self.assertEqual(len(user.phone_local), 10)

    def test_generate_address_jp(self):
        addr = generate_address(country="JP")
        self.assertEqual(addr.country, "JP")
        self.assertTrue(any(ch.isdigit() for ch in addr.postal_code))

    def test_jp_phone_normalize(self):
        e164, local, cc = normalize_phone("JP", "09012345678")
        self.assertEqual(e164, "+819012345678")
        self.assertEqual(cc, "+81")
        self.assertEqual(local, "9012345678")

    def test_region_locale(self):
        r = get_region("JP")
        self.assertEqual(r.locale_tag, "ja_JP")
        self.assertEqual(r.lang, "ja")
        # JS getTimezoneOffset convention: Asia/Tokyo is -540
        self.assertEqual(r.analytics_offset_min, -540)


if __name__ == "__main__":
    unittest.main()
