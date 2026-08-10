import unittest
from unittest.mock import Mock

from paypal.flow import PayPalFlow


class BuyerIdentityModeTests(unittest.TestCase):
    def _make_flow(self, buyer_mode: str):
        flow = PayPalFlow.__new__(PayPalFlow)
        flow.buyer_identity_mode = buyer_mode
        flow.max_flow_attempts = 1
        flow.ba_token = "BA-TEST12345678"
        flow.user = Mock(phone="+6600000000000", email="buyer@example.test")
        flow.proxy_config = Mock(label="代理关闭")
        flow.state = Mock(
            browser_profile={},
            screen={},
            viewport={},
            ba_token="BA-TEST12345678",
        )
        flow._phase0_initial_load = Mock()
        flow._phase2_create_account = Mock()
        flow._phase3_signup_and_2fa = Mock()
        flow._elevate_guest_identity = Mock()
        flow._bind_buyer_to_current_ec = Mock()
        flow._phase4_authorize = Mock(return_value={"status": "ok"})
        flow._with_risk_runtime_report = Mock(return_value={"status": "success"})
        flow._should_retry_full_flow = Mock(return_value=False)
        flow._should_retry_full_flow_exception = Mock(return_value=False)
        flow._risk_runtime_report = Mock(return_value={})
        flow.close = Mock()
        return flow

    def test_elevate_bind_branch_runs_identity_pipeline(self):
        # PAY.153 style identity elevation: Phase3 -> elevate Guest -> bind EC
        # -> authorize with skip_initial_hagrid=True.
        flow = self._make_flow("elevate_bind")
        result = flow.run()

        flow._elevate_guest_identity.assert_called_once()
        flow._bind_buyer_to_current_ec.assert_called_once()
        flow._phase4_authorize.assert_called_once_with(skip_initial_hagrid=True)
        self.assertEqual(result.get("status"), "success")

    def test_legacy_branch_skips_identity_pipeline(self):
        flow = self._make_flow("legacy")
        result = flow.run()

        flow._elevate_guest_identity.assert_not_called()
        flow._bind_buyer_to_current_ec.assert_not_called()
        flow._phase4_authorize.assert_called_once_with()
        self.assertEqual(result.get("status"), "success")

    def test_normalize_buyer_identity_mode_aliases(self):
        # identity_elevation (PAY.153 wording) must map to elevate_bind.
        for raw in ("identity_elevation", "elevate_bind", "elevate", "v2", "guest_bind"):
            self.assertEqual(
                PayPalFlow._normalize_buyer_identity_mode(raw),
                "elevate_bind",
                f"alias {raw!r} should map to elevate_bind",
            )
        for raw in ("legacy", "original", "default", "v1", "", None):
            self.assertEqual(
                PayPalFlow._normalize_buyer_identity_mode(raw),
                "legacy",
                f"alias {raw!r} should map to legacy",
            )




class IdentityElevationFlowTests(unittest.TestCase):
    def test_require_checkout_session_accepts_billing(self):
        from paypal.elevation_flow import IdentityElevationPayPalFlow
        payload = {
            "data": {
                "checkoutSession": {
                    "checkoutSessionType": "BILLING_WITHOUT_PURCHASE",
                    "buyer": {"userId": "U-1"},
                }
            }
        }
        checkout = IdentityElevationPayPalFlow._require_checkout_session(payload)
        self.assertEqual(checkout["checkoutSessionType"], "BILLING_WITHOUT_PURCHASE")

    def test_require_checkout_session_rejects_errors(self):
        from paypal.elevation_flow import IdentityElevationPayPalFlow
        with self.assertRaises(RuntimeError) as ctx:
            IdentityElevationPayPalFlow._require_checkout_session(
                {"errors": [{"message": "NOPE"}]}
            )
        self.assertIn("IDENTITY_ELEVATION_CONTEXT_REJECTED", str(ctx.exception))

    def test_funding_summary(self):
        from paypal.elevation_flow import IdentityElevationPayPalFlow
        summary = IdentityElevationPayPalFlow._funding_summary({
            "fundingOptions": {
                "fundingInstrument": {"id": "FI-1"},
                "allPlans": [
                    {"fundingSources": [{"fundingInstrument": {"id": "FI-2"}}]},
                    {"fundingSources": [{"fundingInstrument": {"id": "FI-3"}}]},
                ],
            }
        })
        self.assertTrue(summary["selected"])
        self.assertTrue(summary["available"])
        self.assertEqual(summary["available_count"], 2)

    def test_elevate_overrides_bind_skip(self):
        from paypal.elevation_flow import IdentityElevationPayPalFlow
        flow = IdentityElevationPayPalFlow.__new__(IdentityElevationPayPalFlow)
        flow.buyer_identity_mode = "elevate_bind"
        flow.max_flow_attempts = 1
        flow.ba_token = "BA-TEST12345678"
        flow.user = Mock(phone="+6600000000000", email="buyer@example.test")
        flow.proxy_config = Mock(label="proxy-off")
        flow.state = Mock(
            browser_profile={}, screen={}, viewport={}, ba_token="BA-TEST",
            euat_token="euat-x", ec_token="EC-TESTTOKEN123", signup_context_ready=True,
            signup_url="https://www.paypal.com/checkoutweb/signup", content_identifier="cid",
            ssrt="ssrt", paypal_client_metadata_id="cmid", user_id="",
        )
        flow.address = Mock(country="BR")
        flow.locale = "pt_BR"
        flow.session = Mock()
        flow._phase0_initial_load = Mock()
        flow._phase2_create_account = Mock()
        flow._phase3_signup_and_2fa = Mock()
        flow._protocol_identity_elevation = Mock(return_value={
            "buyer_ready": True, "user_id": "U-9", "funding_errors": [], "fatal_contingency": ""
        })
        flow._bind_buyer_to_current_ec = Mock(wraps=lambda: IdentityElevationPayPalFlow._bind_buyer_to_current_ec(flow))
        # simulate elevation already set bound flag
        def elevate():
            flow._last_elevation_context = {"buyer_ready": True, "user_id": "U-9"}
            flow._buyer_context_bound = True
            flow._protocol_identity_elevation()
        flow._elevate_guest_identity = elevate
        flow._phase4_authorize = Mock(return_value={"status": "success"})
        flow._with_risk_runtime_report = Mock(side_effect=lambda result: result if isinstance(result, dict) else {"status": "success"})
        flow._should_retry_full_flow = Mock(return_value=False)
        flow._should_retry_full_flow_exception = Mock(return_value=False)
        flow._risk_runtime_report = Mock(return_value={})
        flow.close = Mock()
        # Use parent run path
        from paypal.flow import PayPalFlow
        result = PayPalFlow.run(flow)
        flow._protocol_identity_elevation.assert_called()
        self.assertEqual(result.get("status"), "success")



if __name__ == "__main__":
    unittest.main()
