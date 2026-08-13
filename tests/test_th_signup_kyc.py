"""TH SignUpNewMember KYC payload must match paypal-agreement-protocol-main."""
from __future__ import annotations

import unittest
from unittest.mock import Mock

from paypal.flow import PayPalFlow
from paypal.models import BillingAddress, CardInfo, SessionState, UserInfo, generate_user
from paypal.oaipy_data import generate_thai_national_id
from paypal.protocol import build_protocol, format_billing_line1


class ThSignupKycTests(unittest.TestCase):
    def _make_flow(self, *, ans: bool = False) -> PayPalFlow:
        flow = PayPalFlow.__new__(PayPalFlow)
        flow.ba_token = "BA-TEST"
        flow.user = generate_user("+66812345678", country="TH")
        flow.card = CardInfo(number="4111111111111111", expiry="12/2030", cvv="123")
        flow.address = BillingAddress(
            street="Sukhumvit Road",
            house_number="18",
            district="Pathum Wan",
            city="Bangkok",
            state="Bangkok",
            postal_code="10330",
            country="TH",
        )
        flow.protocol = build_protocol("TH")
        flow.state = SessionState(
            ba_token="BA-TEST",
            content_identifier="TH:th:ad71d3f143dd4ff8804fdf7dc6b3df2b:compliance.signupTerms",
            content_hash="ad71d3f143dd4ff8804fdf7dc6b3df2b",
        )
        flow._billing_address_autocomplete_succeeded = ans
        flow._content_metadata_is_unresolved = lambda: False  # type: ignore
        flow._resolved_content_identifier = (  # type: ignore
            lambda: flow.state.content_identifier
        )
        flow._card_issuer_type = lambda: "VISA"  # type: ignore
        flow._card_expiration_date = lambda: "12/2030"  # type: ignore
        return flow

    def test_thai_national_id_checksum_length(self):
        for _ in range(20):
            value = generate_thai_national_id()
            self.assertEqual(len(value), 13)
            self.assertTrue(value.isdigit())

    def test_th_line1_is_house_first(self):
        line1 = format_billing_line1("th", "Sukhumvit Road", "18")
        self.assertEqual(line1, "18 Sukhumvit Road")

    def test_build_signup_variables_includes_th_kyc(self):
        flow = self._make_flow(ans=False)
        variables = PayPalFlow._build_signup_variables(flow, "EC-TOKEN")
        self.assertEqual(variables.get("nationality"), "TH")
        doc = variables.get("identityDocument")
        self.assertIsInstance(doc, dict)
        self.assertEqual(doc["type"], "NATIONAL_ID")
        self.assertEqual(len(doc["value"]), 13)
        self.assertIn("residentialAddress", variables)
        self.assertEqual(
            variables["residentialAddress"]["line1"],
            variables["billingAddress"]["line1"],
        )
        quality = variables["billingAddress"]["accountQuality"]
        self.assertEqual(quality["autoCompleteType"], "MANUAL")
        self.assertTrue(quality["isUserModified"])
        self.assertFalse(variables.get("marketingOptOut"))

    def test_ans_quality_flags_and_no_regen(self):
        flow = self._make_flow(ans=True)
        # Simulate PayPal-selected Thai line1 already applied.
        flow.address.street = "Soi Number One"
        flow.address.house_number = "89/22"
        flow.address.district = "Prawet"
        flow.address.city = "Bangkok"
        flow.address.state = "Bangkok"
        flow.address.postal_code = "10250"
        before = (
            flow.address.street,
            flow.address.house_number,
            flow.address.postal_code,
        )
        variables = PayPalFlow._build_signup_variables(flow, "EC-TOKEN")
        after = (
            flow.address.street,
            flow.address.house_number,
            flow.address.postal_code,
        )
        self.assertEqual(before, after)
        quality = variables["billingAddress"]["accountQuality"]
        self.assertEqual(quality["autoCompleteType"], "ANS")
        self.assertFalse(quality["isUserModified"])
        self.assertEqual(variables["billingAddress"]["line1"], "89/22 Soi Number One")
        self.assertEqual(
            variables["residentialAddress"]["line1"],
            "89/22 Soi Number One",
        )

    def test_apply_normalized_parses_house_street(self):
        flow = self._make_flow()
        PayPalFlow._apply_paypal_normalized_address(
            flow,
            {
                "line1": "89/22 Soi Number One",
                "line2": "Prawet",
                "city": "Bangkok",
                "state": "Bangkok",
                "postalCode": "10250",
            },
        )
        self.assertEqual(flow.address.house_number, "89/22")
        self.assertEqual(flow.address.street, "Soi Number One")
        self.assertEqual(flow.address.district, "Prawet")

    def test_backfills_kyc_when_user_missing_identity(self):
        """Even a bare UserInfo without identity_* must emit TH KYC fields."""
        flow = self._make_flow(ans=False)
        flow.user = UserInfo(
            first_name="Somchai",
            last_name="Srisuk",
            email="somchai@example.test",
            phone="+66812345678",
            phone_local="812345678",
            phone_country_code="+66",
            password="Test123!",
            dob="15/06/1990",
            # intentionally empty KYC
            national_id="",
            cpf="",
            identity_document_type="",
            identity_document_number="",
            nationality="",
        )
        variables = PayPalFlow._build_signup_variables(flow, "EC-TOKEN")
        self.assertEqual(variables.get("nationality"), "TH")
        doc = variables.get("identityDocument")
        self.assertIsInstance(doc, dict)
        self.assertEqual(doc["type"], "NATIONAL_ID")
        self.assertEqual(len(doc["value"]), 13)
        self.assertIn("residentialAddress", variables)
        # user object itself was backfilled for later retries
        self.assertEqual(flow.user.nationality, "TH")
        self.assertEqual(len(flow.user.identity_document_number), 13)


if __name__ == "__main__":
    unittest.main()
