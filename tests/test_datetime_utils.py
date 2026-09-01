import unittest
from datetime import datetime, timedelta, timezone

from erpnext_whatsapp_connection.datetime_utils import provider_datetime


class ProviderDatetimeTest(unittest.TestCase):
    def test_iso_utc_is_converted_to_naive_site_datetime(self):
        self.assertEqual(
            provider_datetime(
                "2026-09-01T13:52:52.683Z", timezone(timedelta(hours=5))
            ),
            datetime(2026, 9, 1, 18, 52, 52, 683000),
        )

    def test_aware_datetime_is_converted_to_site_timezone(self):
        self.assertEqual(
            provider_datetime(
                datetime(2026, 9, 1, 13, 52, 52, tzinfo=timezone.utc),
                timezone(timedelta(hours=5, minutes=30)),
            ),
            datetime(2026, 9, 1, 19, 22, 52),
        )

    def test_naive_frappe_datetime_is_preserved(self):
        value = datetime(2026, 9, 1, 18, 52, 52)
        self.assertIs(provider_datetime(value, "Asia/Karachi"), value)

    def test_empty_provider_timestamp_remains_empty(self):
        self.assertIsNone(provider_datetime(None, "UTC"))
        self.assertIsNone(provider_datetime("", "UTC"))


if __name__ == "__main__":
    unittest.main()
