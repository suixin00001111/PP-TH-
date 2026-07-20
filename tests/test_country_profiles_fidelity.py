import unittest
from paypal.regions import list_regions_public, get_region
from paypal.oaipy_data import generate_user, generate_address, generate_oaipy_profile, FAKER_LOCALE_BY_COUNTRY
from paypal.protocol import build_protocol


class CountryProfileFidelityTests(unittest.TestCase):
    def test_every_country_has_faker_mapping(self):
        for r in list_regions_public():
            self.assertIn(r["code"], FAKER_LOCALE_BY_COUNTRY)

    def test_profiles_country_code_and_phone(self):
        for r in list_regions_public():
            code = r["code"]
            u = generate_user(country=code)
            a = generate_address(country=code)
            self.assertEqual(a.country, code)
            self.assertTrue(u.phone.startswith(get_region(code).phone_cc), msg=f"{code} {u.phone}")
            self.assertTrue(u.first_name and u.last_name)
            self.assertTrue(a.city and a.street)
            if code == "BR":
                self.assertEqual(len(u.cpf), 11)
            else:
                self.assertEqual(u.cpf, "")

    def test_th_is_not_used_as_identity_for_others(self):
        u = generate_user(country="JP")
        a = generate_address(country="JP")
        self.assertEqual(a.country, "JP")
        self.assertTrue(u.phone.startswith("+81"))
        self.assertFalse(u.phone.startswith("+66"))

    def test_profile_meta_marks_open_source(self):
        p = generate_oaipy_profile(country="US")
        self.assertIn("Faker", p["meta"]["data_source"])
        self.assertEqual(p["meta"]["protocol_reference"], "TH state machine")
        self.assertEqual(p["address"].country, "US")

    def test_protocol_aligns_with_profile_country(self):
        for code in ("TH", "JP", "US", "BR", "DE", "KR"):
            proto = build_protocol(code)
            a = generate_address(country=code)
            self.assertEqual(proto.code, a.country)


if __name__ == "__main__":
    unittest.main()
