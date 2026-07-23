import unittest

from web import WebJob, normalize_thailand_phone, sanitize_payload


class WebHelperTests(unittest.TestCase):
    def test_thailand_phone_is_normalized(self):
        self.assertEqual(normalize_thailand_phone("+66 81 234 5678"), "+66812345678")
        self.assertEqual(normalize_thailand_phone("0812345678"), "+66812345678")
        self.assertEqual(normalize_thailand_phone("66812345678"), "+66812345678")

    def test_non_thailand_mobile_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_thailand_phone("+5511987654321")
        with self.assertRaises(ValueError):
            normalize_thailand_phone("+819012345678")

    def test_error_result_is_not_marked_completed(self):
        job = WebJob(
            id="test-job",
            owner_device_id="a" * 32,
            ba_token="BA-TEST12345678",
            phone="+66812345678",
        )

        job.complete({"status": "error", "error": "authorize failed"})

        self.assertEqual(job.status, "failed")
        self.assertEqual(job.stage, "执行失败")
        self.assertEqual(job.error, "authorize failed")

    def test_session_cookies_are_not_returned_to_ui(self):
        payload = sanitize_payload({"session_cookies": [{"name": "sid", "value": "secret"}]})
        self.assertEqual(payload["session_cookies"], "<redacted>")


if __name__ == "__main__":
    unittest.main()
