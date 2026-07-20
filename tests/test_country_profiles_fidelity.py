import unittest
from paypal.regions import list_regions_public, get_region
from paypal.oaipy_data import generate_user, generate_address, NAMES, CITIES, STREETS
from paypal.protocol import build_protocol


class CountryProfileFidelityTests(unittest.TestCase):
    def test_every_country_has_name_city_street_pool(self):
        for r in list_regions_public():
            code = r["code"]
            self.assertIn(code, NAMES, msg=f"missing names for {code}")
            self.assertIn(code, CITIES, msg=f"missing cities for {code}")
            self.assertIn(code, STREETS, msg=f"missing streets for {code}")

    def test_profiles_match_country_not_thailand_leak(self):
        th_first, th_last = set(NAMES["TH"][0]), set(NAMES["TH"][1])
        th_cities = {c[1] for c in CITIES["TH"]}
        th_streets = set(STREETS["TH"])
        for r in list_regions_public():
            code = r["code"]
            # sample several times for leak detection
            for _ in range(8):
                u = generate_user(country=code)
                a = generate_address(country=code)
                self.assertEqual(a.country, code)
                self.assertTrue(u.phone.startswith(get_region(code).phone_cc))
                if code != "TH":
                    self.assertNotIn(a.city, th_cities)
                    self.assertNotIn(a.street, th_streets)
                    # names must come from country pool
                    self.assertIn(u.first_name, NAMES[code][0])
                    self.assertIn(u.last_name, NAMES[code][1])
                else:
                    self.assertIn(u.first_name, th_first)
                    self.assertIn(u.last_name, th_last)

    def test_protocol_and_profile_align(self):
        for code in ("TH", "JP", "US", "BR", "DE", "KR", "CN", "MX", "ID"):
            p = build_protocol(code)
            u = generate_user(country=code)
            a = generate_address(country=code)
            self.assertEqual(p.code, a.country)
            self.assertTrue(u.phone.startswith(p.phone_cc))
            if code == "BR":
                self.assertEqual(len(u.cpf), 11)
            else:
                self.assertEqual(u.cpf, "")


if __name__ == "__main__":
    unittest.main()
