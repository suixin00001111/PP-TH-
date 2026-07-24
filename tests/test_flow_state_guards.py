import json
import unittest
from unittest.mock import Mock, patch

from paypal.flow import PayPalFlow
from paypal.models import BillingAddress, CardInfo, SessionState, UserInfo
from paypal.proxy import ProxyConfig
from paypal.protocol import build_protocol


EC_TOKEN = "EC-ABC123456789"
CONTENT_HASH = "a" * 32
SIGNUP_HTML = (
    "<html><body>checkoutweb"
    + ("x" * 120)
    + "<script>window.__INITIAL_DATA__ = "
    + json.dumps(
        {
            "contentHash": CONTENT_HASH,
            "contentIdentifier": f"BR:pt:{CONTENT_HASH}:compliance.signupTerms",
        }
    )
    + ";</script></body></html>"
)


class FakeResponse:
    def __init__(self, status_code=200, url="https://www.paypal.com/pay", text="", headers=None):
        self.status_code = status_code
        self.url = url
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = headers or {}


class FakeSession:
    def __init__(self, *, posts=None, gets=None, checkout_result=None):
        self.posts = list(posts or [])
        self.gets = list(gets or [])
        self.checkout_result = checkout_result or {
            "data": {"checkoutSession": {"checkoutSessionType": "BILLING_WITHOUT_PURCHASE"}}
        }
        self.graphql_calls = []
        self.post_calls = []
        self.get_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        if not self.posts:
            raise AssertionError(f"Unexpected POST: {url}")
        return self.posts.pop(0)

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        if not self.gets:
            raise AssertionError(f"Unexpected GET: {url}")
        return self.gets.pop(0)

    def graphql(self, operation_name, query, variables, **kwargs):
        self.graphql_calls.append((operation_name, variables, kwargs))
        if operation_name == "CheckoutSessionDataQuery":
            return self.checkout_result
        return {"data": {}}

    def close(self):
        return None


def make_flow(session, *, action_ids=False):
    flow = PayPalFlow.__new__(PayPalFlow)
    flow.ba_token = "BA-TEST12345678"
    flow.user = UserInfo(
        first_name="Ana",
        last_name="Silva",
        email="ana@example.test",
        phone="5511999999999",
        phone_local="11999999999",
        phone_country_code="+55",
        password="Test123!",
        dob="01/01/1990",
        cpf="123.456.789-00",
    )
    flow.card = CardInfo(number="4111111111111111", expiry="12/2030", cvv="123")
    flow.address = BillingAddress(
        street="Avenida Paulista",
        house_number="1000",
        district="Bela Vista",
        city="Sao Paulo",
        state="SP",
        postal_code="01310-100",
        country="TH",
    )
    flow.max_card_attempts = 1
    flow.state = SessionState(
        ba_token=flow.ba_token,
        ssrt="123456",
        ctx_id="ctx-test",
        show_create_account_action_id="show-action" if action_ids else "",
        create_user_action_id="create-action" if action_ids else "",
    )
    flow.session = session
    flow.proxy_config = ProxyConfig(enabled=False)
    flow.protocol = build_protocol(flow.address.country or "TH")
    flow.lang = flow.protocol.lang
    flow.fingerprint_source = "random"
    flow.datadome_mode = "protocol"
    flow.mtr_runtime = "python_generated"
    flow.risk_signals_mode = "protocol"
    flow.runtime_mode = "protocol"
    flow._roxy_runtime_disabled_reason = ""
    flow._requested_risk_signals_mode = "protocol"
    flow.sms_provider = None
    flow._datadome_browser_document = {}
    flow._used_partial_signup_token = False
    flow._billing_address_autocomplete_succeeded = False
    flow._roxy_skipped_telemetry_families = set()
    flow._signup_billing_address_prepared = False
    flow._headless_session = None
    flow._headless_optimized_session = None
    flow.captcha_bypass_mode = "off"
    return flow


def patched_signals():
    return patch.multiple(
        "paypal.flow",
        build_fn_sync_data=Mock(return_value="fn-sync"),
        send_tealeaf_data=Mock(),
        send_observability_emit=Mock(),
        send_weasley_log=Mock(),
        send_device_fingerprint=Mock(),
        send_da_bootstrap=Mock(),
        send_fraudnet_rdt=Mock(),
        send_signup_field_events=Mock(),
        send_identity_di_log=Mock(),
        send_datadog_rum_action=Mock(return_value=None),
        send_analytics_ts=Mock(),
    )


class FlowStateGuardTests(unittest.TestCase):
    def test_phase0_datadome_fails_without_empty_token_post(self):
        # Brazil-depth protocol fallback still tries the empty-token POST once.
        # If the challenge remains, Phase 0 must fail hard (no silent continue).
        session = FakeSession(
            gets=[FakeResponse(status_code=403, text="DataDome challenge") for _ in range(4)],
            posts=[FakeResponse(status_code=403, text="DataDome challenge still blocked")],
        )
        flow = make_flow(session)

        with patch("paypal.flow.PayPalSession", return_value=session), patch("paypal.flow.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "DataDome challenge"):
                flow._phase0_initial_load()

        self.assertEqual(len(session.post_calls), 1)

    def test_missing_modxo_ids_cannot_continue_without_ec(self):
        session = FakeSession(
            posts=[FakeResponse(status_code=200, text="legacy form did not transition")]
        )
        flow = make_flow(session, action_ids=False)

        with patched_signals(), self.assertRaisesRegex(RuntimeError, "no valid EC token"):
            flow._phase2_create_account()

        self.assertEqual(session.graphql_calls, [])

    def test_generic_error_redirect_is_rejected(self):
        session = FakeSession(
            posts=[
                FakeResponse(
                    status_code=302,
                    url="https://www.paypal.com/pay?token=BA-TEST12345678",
                    headers={"Location": "/pay/generic-error?code=invalid"},
                )
            ]
        )
        flow = make_flow(session, action_ids=False)

        with patched_signals(), self.assertRaisesRegex(RuntimeError, "generic-error"):
            flow._phase2_create_account()

        self.assertEqual(session.graphql_calls, [])

    def test_modxo_transition_without_ec_is_rejected(self):
        session = FakeSession(
            posts=[
                FakeResponse(status_code=200, text="pay action ok"),
                FakeResponse(
                    status_code=200,
                    text=(
                        '{"onboardingRedirectUrl":'
                        '"https://www.paypal.com/checkoutweb/signup?country.x=BR"}'
                    ),
                ),
            ],
            gets=[
                FakeResponse(
                    status_code=200,
                    url="https://www.paypal.com/checkoutweb/signup?country.x=BR",
                    text=SIGNUP_HTML,
                )
            ],
        )
        flow = make_flow(session, action_ids=True)

        with patched_signals(), self.assertRaisesRegex(RuntimeError, "no valid EC token"):
            flow._phase2_create_account()

        self.assertEqual(session.graphql_calls, [])

    def test_valid_ec_signup_and_checkout_context_is_accepted(self):
        onboarding_url = f"https://www.paypal.com/checkoutweb/signup?token={EC_TOKEN}"
        session = FakeSession(
            posts=[
                FakeResponse(status_code=200, text="pay action ok"),
                FakeResponse(
                    status_code=200,
                    text=json.dumps({"onboardingRedirectUrl": onboarding_url}),
                ),
            ],
            gets=[
                FakeResponse(status_code=200, url=onboarding_url, text=SIGNUP_HTML),
                FakeResponse(status_code=200, url=onboarding_url, text=SIGNUP_HTML),
            ],
        )
        flow = make_flow(session, action_ids=True)

        with patched_signals():
            flow._phase2_create_account()

        self.assertEqual(flow.state.ec_token, EC_TOKEN)
        self.assertTrue(flow.state.signup_context_ready)
        token_calls = [variables["token"] for _, variables, _ in session.graphql_calls if "token" in variables]
        self.assertTrue(token_calls)
        self.assertEqual(set(token_calls), {EC_TOKEN})

    def test_phase3_refuses_ba_token_fallback(self):
        flow = make_flow(FakeSession())
        flow.state.ec_token = ""
        flow.state.signup_url = "https://www.paypal.com/checkoutweb/signup"
        flow.state.signup_context_ready = True

        with patched_signals(), self.assertRaisesRegex(RuntimeError, "refusing to substitute"):
            flow._phase3_signup_and_2fa()

    def test_phase0_hard_datadome_page_fails_after_load(self):
        # 200 challenge page (no empty-token POST path) must still hard-fail before
        # static ModXO action ids are trusted for Phase 2.
        session = FakeSession(
            gets=[
                FakeResponse(
                    status_code=200,
                    url="https://www.paypal.com/agreements/approve?ba_token=BA-TEST12345678",
                    text=(
                        "<html><body>paypal-authchallenge captcha-delivery.com "
                        "device_check_redirect_to_slider</body></html>"
                    ),
                )
            ],
        )
        flow = make_flow(session)

        with patch("paypal.flow.PayPalSession", return_value=session), patch("paypal.flow.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, r"Phase 0 still blocked by DataDome"):
                flow._phase0_initial_load()

        self.assertEqual(session.post_calls, [])

    def test_ineligible_modxo_redirect_is_rejected(self):
        ineligible_url = (
            "https://www.paypal.com/checkoutweb/signup?modxo_redirect_reason=ineligible"
            "&country.x=NL&ba_token=BA-TEST12345678"
        )
        session = FakeSession(
            posts=[
                FakeResponse(status_code=200, text="pay action ok"),
                FakeResponse(
                    status_code=200,
                    text=json.dumps({"onboardingRedirectUrl": ineligible_url}),
                ),
            ],
        )
        flow = make_flow(session, action_ids=True)

        with patched_signals(), self.assertRaisesRegex(
            RuntimeError,
            r"modxo_redirect_reason=ineligible",
        ):
            flow._phase2_create_account()

        self.assertEqual(session.graphql_calls, [])
        self.assertEqual(session.get_calls, [])

    def test_datadome_and_ineligible_errors_are_not_full_flow_retryable(self):
        self.assertFalse(
            PayPalFlow._should_retry_full_flow_exception(
                RuntimeError(
                    "Phase 0 still blocked by DataDome/challenge page after load (status=403)."
                )
            )
        )
        self.assertFalse(
            PayPalFlow._should_retry_full_flow_exception(
                RuntimeError(
                    "PayPal ModXO redirect reason=ineligible: BA token/session is not eligible "
                    "for guest create-account checkout."
                )
            )
        )
        self.assertTrue(
            PayPalFlow._should_retry_full_flow_exception(
                RuntimeError(
                    "Create account flow did not produce an EC checkout token (no valid EC token)."
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
