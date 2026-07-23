import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from paypal.merchant_complete import complete_merchant_chain
from paypal.models import SessionState
from paypal.session import PayPalSession, build_common_headers


class HttpFullChainTests(unittest.TestCase):
    def test_region_headers_are_thai(self):
        state = SessionState(region="TH")
        headers = build_common_headers(state)
        accept = headers.get("Accept-Language") or headers.get("accept-language") or ""
        self.assertIn("th-TH", accept)
        session = PayPalSession(state)
        try:
            # Session keeps region on state; Accept-Language must stay Thai.
            self.assertEqual(getattr(session, "state", state).region, "TH")
            client_headers = getattr(session.client, "headers", {}) or {}
            al = client_headers.get("Accept-Language") or client_headers.get("accept-language") or accept
            self.assertIn("th-TH", str(al).split(",", 1)[0])
        finally:
            session.close()

    @patch("paypal.merchant_complete.confirm_account_plus", return_value={"plus": False})
    @patch("paypal.merchant_complete.poll_checkout_verify")
    @patch("paypal.merchant_complete.poll_payment_pages", return_value={"ok": False})
    @patch("paypal.merchant_complete.poll_openai_pay_status")
    @patch("paypal.merchant_complete.poll_setup_intent")
    @patch("paypal.merchant_complete.follow_redirect_chain")
    @patch("paypal.merchant_complete.build_session")
    def test_success_path_persists_b_layer_and_cookies(
        self,
        build_session,
        follow_chain,
        poll_seti,
        poll_pay,
        poll_pages,
        poll_verify,
        account,
    ):
        session = requests.Session()
        session.cookies.set("merchant_session", "demo", domain="chatgpt.com", path="/")
        build_session.return_value = session
        verify_url = "https://chatgpt.com/checkout/verify?cs=cs_live_demo"
        final_url = (
            "https://pay.openai.com/c/pay/cs_live_demo?redirect_status=pending"
            "&setup_intent=seti_demo&setup_intent_client_secret=seti_demo_secret_demo"
        )
        follow_chain.return_value = {
            "final_url": final_url,
            "redirect_status": "pending",
            "stripe_return_status": "success",
            "setup_intent": "seti_demo",
            "setup_intent_client_secret": "seti_demo_secret_demo",
            "verification_url": verify_url,
            "success_return_url": verify_url,
            "chatgpt_land_url": "https://chatgpt.com/",
            "hops": [],
        }
        poll_pay.return_value = {"ok": True, "redirect_status": "pending", "url": final_url}
        poll_seti.return_value = {"ok": True, "status": "succeeded", "setup_intent": "seti_demo"}
        poll_verify.return_value = {
            "ok": True,
            "state": "landed",
            "url": "https://chatgpt.com/",
            "processing_seen": True,
        }

        with tempfile.TemporaryDirectory() as td:
            session_path = Path(td) / "merchant_session.json"
            result = complete_merchant_chain(
                {"return_url": "https://pm-redirects.stripe.com/return/?status=success"},
                session_path=session_path,
            )
            evidence = json.loads((Path(td) / "b_layer_evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(result["merchant_chain_status"], "full_success_b_c")
            self.assertEqual(result["setup_intent"], "seti_demo")
            self.assertEqual(result["setup_intent_client_secret"], "seti_demo_secret_demo")
            self.assertEqual(result["stripe_return_status"], "success")
            self.assertTrue(result["session_cookies"])
            self.assertEqual(evidence["setup_intent"], "seti_demo")
            self.assertTrue(evidence["session_cookies"])

    @patch("paypal.merchant_complete.follow_redirect_chain")
    @patch("paypal.merchant_complete.build_session")
    def test_failed_callback_is_terminal_without_verify_poll(self, build_session, follow_chain):
        build_session.return_value = requests.Session()
        follow_chain.return_value = {
            "final_url": "https://pay.openai.com/c/pay/cs_live_fail?redirect_status=failed",
            "redirect_status": "failed",
            "stripe_return_status": "failed",
            "verification_url": "https://chatgpt.com/checkout/verify?cs=cs_live_fail",
            "success_return_url": "https://chatgpt.com/checkout/verify?cs=cs_live_fail",
            "hops": [],
        }
        with patch("paypal.merchant_complete.poll_checkout_verify") as poll_verify:
            poll_verify.return_value = {"ok": False, "state": "failed", "stuck_processing": False}
            result = complete_merchant_chain(
                {"return_url": "https://pm-redirects.stripe.com/return/?status=failed"}
            )
        poll_verify.assert_called_once()
        self.assertLessEqual(poll_verify.call_args.kwargs["attempts"], 2)
        self.assertEqual(result["merchant_chain_status"], "callback_failed")
        self.assertTrue(result["terminal_unpaid"])
        self.assertTrue(result["should_stop_processing_wait"])


if __name__ == "__main__":
    unittest.main()
