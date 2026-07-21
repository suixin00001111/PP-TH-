import unittest
from paypal.smsbower_countries import resolve_smsbower_country_id, SMSBOWER_COUNTRY_IDS, list_mapped_iso_codes


class SMSBowerCountryMapTests(unittest.TestCase):
    def test_core_markets_mapped(self):
        expected = {
            "BR": "73",
            "TH": "52",
            "US": "12",
            "GB": "16",
            "ID": "6",
            "PH": "4",
            "JP": "182",
            "IN": "22",
            "MX": "54",
            "DE": "43",
            "FR": "78",
        }
        for iso, sid in expected.items():
            self.assertEqual(resolve_smsbower_country_id(iso), sid, iso)

    def test_explicit_override(self):
        self.assertEqual(resolve_smsbower_country_id("JP", explicit="999"), "999")

    def test_map_size(self):
        self.assertGreaterEqual(len(list_mapped_iso_codes()), 80)


if __name__ == "__main__":
    unittest.main()
