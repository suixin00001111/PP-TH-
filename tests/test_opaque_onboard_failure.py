import unittest
from pathlib import Path
from unittest.mock import Mock

from paypal.flow import PayPalFlow


class OpaqueOnboardFailureTests(unittest.TestCase):
    def test_omit_null_signup_fields(self):
        cleaned = PayPalFlow._omit_null_signup_fields(
            {
                "email": "a@b.com",
                "identityDocument": None,
                "crsData": None,
                "legalAgreements": {},
            }
        )
        self.assertEqual(cleaned, {"email": "a@b.com", "legalAgreements": {}})
        self.assertNotIn("identityDocument", cleaned)
        self.assertNotIn("crsData", cleaned)

    def test_opaque_destructure_failure_is_retryable(self):
        errors = [
            {
                "message": "Cannot destructure property 'index' of 'error' as it is undefined.",
                "path": ["onboardAccount"],
                "extensions": {"class": "FAILURE"},
                "statusCode": 200,
            }
        ]
        self.assertTrue(PayPalFlow._is_opaque_onboard_failure_retryable(errors))

    def test_structured_card_error_is_not_opaque_retryable(self):
        errors = [
            {
                "message": "R_ERROR",
                "path": ["onboardAccount"],
                "checkpoints": ["addCard"],
                "errorData": {"0": {"field": "cardNumber", "code": "CARD_GENERIC_ERROR"}},
                "extensions": {"class": "ERROR"},
            }
        ]
        self.assertFalse(PayPalFlow._is_opaque_onboard_failure_retryable(errors))

    def test_identity_document_omitted_for_th(self):
        flow = Mock()
        flow.address = Mock(country="TH")
        flow.protocol = Mock(send_identity_document=False, identity_type=None)
        flow.user = Mock(cpf="", national_id="")
        # Bind real method
        result = PayPalFlow._identity_document_payload(flow)
        self.assertIsNone(result)



    def test_dob_payload_never_empty(self):
        flow = Mock()
        flow.user = Mock(dob="")
        payload = PayPalFlow._dob_payload(flow)
        self.assertEqual(set(payload), {"day", "month", "year"})
        self.assertTrue(all(payload.values()))

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
        flow._signup_billing_address_prepared = True
        flow._billing_address_autocomplete_succeeded = True
        flow._form_safe_address_text = lambda value, fallback="": PayPalFlow._form_safe_address_text(value, fallback=fallback)
        PayPalFlow._ensure_form_safe_billing_address(flow)
        self.assertNotEqual(str(flow.address.state).upper(), "ST")
        joined = f"{flow.address.street}{flow.address.city}{flow.address.state}{flow.address.district}"
        self.assertTrue(all(ord(ch) < 128 for ch in joined))
        self.assertNotEqual(flow.address.postal_code, "00000")


if __name__ == "__main__":
    unittest.main()
