import os
import unittest
from unittest.mock import patch

from paypal.models import BillingAddress
from paypal.oaipy_data import generate_address
from paypal import online_address as oa
from paypal.online_address import (
    online_address_enabled,
    try_resolve_online_address,
    validate_address_basic,
    _payload,
)


class OnlineAddressTests(unittest.TestCase):
    def test_online_enabled_default(self):
        old = os.environ.pop("PAYPAL_ONLINE_ADDRESS", None)
        try:
            self.assertTrue(online_address_enabled())
            self.assertFalse(online_address_enabled(False))
            self.assertTrue(online_address_enabled(True))
            os.environ["PAYPAL_ONLINE_ADDRESS"] = "0"
            self.assertFalse(online_address_enabled())
        finally:
            if old is None:
                os.environ.pop("PAYPAL_ONLINE_ADDRESS", None)
            else:
                os.environ["PAYPAL_ONLINE_ADDRESS"] = old

    def test_validate_basic_requires_core_fields(self):
        errors = validate_address_basic({}, {"street": "", "house_number": "1", "city": "X"})
        self.assertTrue(any("street" in e for e in errors))

    def test_try_resolve_returns_none_when_disabled(self):
        self.assertIsNone(try_resolve_online_address("BR", enabled=False))

    def test_generate_address_prefers_online(self):
        fake = BillingAddress(
            street="Rua Augusta",
            house_number="1500",
            district="Consolacao",
            city="Sao Paulo",
            state="SP",
            postal_code="01304-001",
            country="XX",
        )
        with patch.object(oa, "try_resolve_online_address", return_value=fake):
            addr = generate_address("BR", prefer_online=True)
        self.assertEqual(addr.street, "Rua Augusta")
        self.assertEqual(addr.country, "BR")
        self.assertEqual(addr.postal_code, "01304-001")

    def test_generate_address_falls_back_local(self):
        with patch.object(oa, "try_resolve_online_address", return_value=None):
            addr = generate_address("TH", prefer_online=True)
        self.assertEqual(addr.country, "TH")
        self.assertTrue(addr.street)
        self.assertTrue(addr.city)

    def test_generate_address_can_skip_online(self):
        with patch.object(oa, "try_resolve_online_address") as mocked:
            addr = generate_address("JP", prefer_online=False)
            mocked.assert_not_called()
            self.assertEqual(addr.country, "JP")
            self.assertTrue(addr.city)

    def test_payload_keys(self):
        addr = BillingAddress("Main", "1", "D", "City", "ST", "10000", "US")
        payload = _payload(addr)
        self.assertIn("postalCode", payload)
        self.assertIn("line1", payload)


if __name__ == "__main__":
    unittest.main()
