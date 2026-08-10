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


if __name__ == "__main__":
    unittest.main()
