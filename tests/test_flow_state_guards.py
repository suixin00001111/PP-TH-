import json
import unittest
from unittest.mock import Mock, patch

from paypal.flow import PayPalFlow
from paypal.models import BillingAddress, CardInfo, SessionState, UserInfo
from paypal.proxy import ProxyConfig


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
    return flow


def patched_signals():
    return patch.multiple(
        "paypal.flow",
        build_fn_sync_data=Mock(return_value="fn-sync"),
        send_tealeaf_data=Mock(),
        send_observability_emit=Mock(),
        send_weasley_log=Mock(),
        send_device_fingerprint=Mock(),
    )


class FlowStateGuardTests(unittest.TestCase):
    def test_phase0_datadome_fails_without_empty_token_post(self):
        session = FakeSession(
            gets=[FakeResponse(status_code=403, text="DataDome challenge") for _ in range(4)]
        )
        flow = make_flow(session)

        with patch("paypal.flow.PayPalSession", return_value=session), patch("paypal.flow.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "DataDome challenge"):
                flow._phase0_initial_load()

        self.assertEqual(session.post_calls, [])

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


if __name__ == "__main__":
    unittest.main()
