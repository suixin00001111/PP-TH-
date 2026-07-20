import unittest
from paypal.regions import list_regions_public, get_region, normalize_phone
from paypal.oaipy_data import generate_user, generate_address


class ProtocolProfileTests(unittest.TestCase):
    def test_all_share_th_base(self):
        for r in list_regions_public():
            prof = get_region(r["code"])
            self.assertEqual(prof.protocol_base, "TH")
            self.assertTrue(prof.lang)
            self.assertTrue(prof.locale_tag)
            self.assertTrue(prof.phone_cc.startswith("+"))

    def test_br_has_cpf(self):
        user = generate_user(phone="+5511987654321", country="BR")
        self.assertEqual(user.phone_country_code, "+55")
        self.assertEqual(len(user.cpf), 11)
        self.assertTrue(user.cpf.isdigit())
        addr = generate_address(country="BR")
        self.assertEqual(addr.country, "BR")
        self.assertTrue(get_region("BR").send_identity_document)

    def test_th_no_identity(self):
        self.assertFalse(get_region("TH").send_identity_document)
        user = generate_user(phone="+66812345678", country="TH")
        self.assertEqual(user.cpf, "")

    def test_jp_us_locale(self):
        self.assertEqual(get_region("JP").locale_tag, "ja_JP")
        self.assertEqual(get_region("US").lang, "en")
        e164, _, cc = normalize_phone("DE", "15123456789")
        self.assertTrue(e164.startswith("+49"))
        self.assertEqual(cc, "+49")


if __name__ == "__main__":
    unittest.main()
