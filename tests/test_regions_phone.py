import unittest
from paypal.regions import normalize_phone, get_region, list_regions_public, normalize_region
from paypal.oaipy_data import generate_user, generate_address


class MultiRegionTests(unittest.TestCase):
    def test_many_regions_listed(self):
        regions = list_regions_public()
        codes = {r["code"] for r in regions}
        for c in ("TH", "JP", "US", "GB", "BR", "MX", "ID"):
            self.assertIn(c, codes)
        self.assertGreaterEqual(len(regions), 20)

    def test_phone_only_requires_dial_code_semantics(self):
        # local-only accepted and prefixed
        e164, local, cc = normalize_phone("US", "2025550123")
        self.assertEqual(cc, "+1")
        self.assertTrue(e164.startswith("+1"))
        self.assertEqual(local, "2025550123")

        e164, local, cc = normalize_phone("GB", "+447400123456")
        self.assertEqual(cc, "+44")
        self.assertTrue(e164.startswith("+44"))

        e164, local, cc = normalize_phone("TH", "0812345678")
        self.assertEqual(e164, "+66812345678")

    def test_profile_country(self):
        for code in ("TH", "JP", "US", "BR", "DE"):
            u = generate_user(country=code)
            a = generate_address(country=code)
            self.assertEqual(a.country, code)
            self.assertTrue(u.phone.startswith(get_region(code).phone_cc))

    def test_invalid_region(self):
        with self.assertRaises(ValueError):
            normalize_region("XX")


if __name__ == "__main__":
    unittest.main()
