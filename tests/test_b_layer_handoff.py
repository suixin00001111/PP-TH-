import json
import tempfile
import unittest
from pathlib import Path

from paypal.b_layer_handoff import build_b_layer_evidence, persist_b_layer_evidence


class BLayerHandoffTests(unittest.TestCase):
    def test_build_from_return_url(self):
        result = {
            "status": "success",
            "return_url": (
                "https://pay.openai.com/pm-redirects?"
                "setup_intent=seti_abc123&setup_intent_client_secret=seti_abc123_secret_xyz"
                "&redirect_status=succeeded"
            ),
            "billing_agreement_id": "B-TEST",
        }
        b = build_b_layer_evidence(result)
        self.assertEqual(b["region"], "TH")
        self.assertTrue(b["return_url"].startswith("https://"))
        self.assertEqual(b["setup_intent"], "seti_abc123")
        self.assertIn("secret", b["setup_intent_client_secret"])
        self.assertEqual(b["stripe_return_status"], "succeeded")
        self.assertEqual(b["protocol_mode"], "http_only_full_protocol")

    def test_persist_files(self):
        with tempfile.TemporaryDirectory() as td:
            path = persist_b_layer_evidence(
                td,
                {"return_url": "https://example.com/return?redirect_status=pending"},
            )
            self.assertTrue(path.exists())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["stripe_return_status"], "pending")
            replay = Path(td) / "merchant_replay_input.json"
            self.assertTrue(replay.exists())


if __name__ == "__main__":
    unittest.main()
