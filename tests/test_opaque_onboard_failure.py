import unittest
from pathlib import Path
from unittest.mock import Mock

from paypal.flow import PayPalFlow


class OpaqueOnboardFailureTests(unittest.TestCase):
    def test_identity_document_required_for_th(self):
        """TH Weasley form requires NATIONAL_ID; omitting it yields opaque FAILURE."""
        from paypal.protocol import build_protocol
        from paypal.oaipy_data import generate_user

        flow = Mock()
        flow.address = Mock(country="TH")
        flow.protocol = build_protocol("TH")
        flow.user = generate_user("+66812345678", country="TH")
        result = PayPalFlow._identity_document_payload(flow)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "NATIONAL_ID")
        self.assertEqual(len(result["value"]), 13)
        self.assertTrue(result["value"].isdigit())

    def test_dob_payload_shape(self):
        # Valid dob -> full dict; malformed/missing dob -> empty dict (no default).
        flow = Mock()
        flow.user = Mock(dob="15/06/1990")
        payload = PayPalFlow._dob_payload(flow)
        self.assertEqual(payload, {"day": "15", "month": "06", "year": "1990"})

        flow.user = Mock(dob="")
        payload = PayPalFlow._dob_payload(flow)
        self.assertEqual(payload, {})

    def test_diag_write_json_writes_somewhere(self):
        written = PayPalFlow._diag_write_json(
            "paypal_diag_smoke_last.json",
            {"ok": True, "source": "unit-test"},
        )
        self.assertTrue(written)
        self.assertTrue(any(Path(path).exists() for path in written))


    def test_th_address_generation_is_ascii_and_coherent(self):
        from paypal.oaipy_data import generate_address
        for _ in range(8):
            addr = generate_address(country="TH")
            for field in (addr.street, addr.district, addr.city, addr.state, addr.house_number, addr.postal_code):
                self.assertTrue(all(ord(ch) < 128 for ch in str(field)))
            self.assertNotEqual(str(addr.state).upper(), "ST")
            self.assertEqual(addr.country, "TH")
            self.assertTrue(str(addr.postal_code).isdigit())
            self.assertGreaterEqual(len(str(addr.postal_code)), 5)

    def test_ensure_form_safe_billing_address_replaces_bad_th(self):
        from paypal.models import BillingAddress
        bad = BillingAddress(
            street="ถนนสุขุมวิท",
            house_number="12",
            district="ปทุมวัน",
            city="กรุงเทพ",
            state="ST",
            postal_code="00000",
            country="TH",
        )
        flow = Mock()
        flow.address = bad
        flow.protocol = Mock(code="TH")
        flow._signup_billing_address_prepared = False
        # Pre-ANS: Thai-script/ST noise must be replaced with curated ASCII.
        flow._billing_address_autocomplete_succeeded = False
        flow._form_safe_address_text = lambda value, fallback="": PayPalFlow._form_safe_address_text(value, fallback=fallback)
        PayPalFlow._ensure_form_safe_billing_address(flow)
        self.assertNotEqual(str(flow.address.state).upper(), "ST")
        joined = f"{flow.address.street}{flow.address.city}{flow.address.state}{flow.address.district}"
        self.assertTrue(all(ord(ch) < 128 for ch in joined))
        self.assertNotEqual(flow.address.postal_code, "00000")

    def test_ensure_form_safe_preserves_ans_selection(self):
        """After PayPal ANS, do not regenerate away from the selected address."""
        from paypal.models import BillingAddress
        ans = BillingAddress(
            street="ซอย นัมเบอร์วัน",
            house_number="89/22",
            district="ประเวศ",
            city="กรุงเทพมหานคร",
            state="ST",
            postal_code="10250",
            country="TH",
        )
        flow = Mock()
        flow.address = ans
        flow.protocol = Mock(code="TH")
        flow._billing_address_autocomplete_succeeded = True
        PayPalFlow._ensure_form_safe_billing_address(flow)
        self.assertEqual(flow.address.house_number, "89/22")
        self.assertEqual(flow.address.street, "ซอย นัมเบอร์วัน")
        self.assertEqual(flow.address.postal_code, "10250")
        # Only invalid state is coerced; Thai script from ANS is kept.
        self.assertNotEqual(str(flow.address.state).upper(), "ST")



if __name__ == "__main__":
    unittest.main()
