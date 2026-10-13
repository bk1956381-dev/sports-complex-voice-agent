import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from app.tools.booking import create_booking
from app.tools.validation import KARACHI


class BookingDateSafetyTests(unittest.TestCase):
    def setUp(self):
        self.booking_details = {
            "facility": "tennis",
            "start_time": "10:00",
            "end_time": "11:00",
            "customer_name": "Date Safety Test",
            "customer_phone": "03000000000",
            "customer_email": "date-safety@example.invalid",
        }
        self.facility = {
            "id": 1,
            "name": "Tennis Court",
            "rate": 2000,
            "opening_time": "08:00:00",
            "closing_time": "23:00:00",
        }

    def _assert_rejected_before_side_effects(self, booking_date, start_time):
        details = {
            **self.booking_details,
            "date": booking_date,
            "start_time": start_time,
        }
        with (
            patch("app.tools.booking.get_facility_record", return_value=self.facility),
            patch("app.tools.booking.get_connection") as get_connection,
            patch("app.tools.booking.create_calendar_event") as create_event,
            patch("app.tools.booking.send_booking_email") as send_email,
        ):
            result = create_booking(**details)

        self.assertFalse(result["success"])
        self.assertTrue(result["message"])
        get_connection.assert_not_called()
        create_event.assert_not_called()
        send_email.assert_not_called()

    def test_past_date_is_rejected_before_side_effects(self):
        yesterday = (datetime.now(KARACHI).date() - timedelta(days=1)).isoformat()
        self._assert_rejected_before_side_effects(yesterday, "10:00")

    def test_past_start_time_is_rejected_before_side_effects(self):
        now = datetime.now(KARACHI)
        past_start = (now - timedelta(minutes=5)).strftime("%H:%M")
        self._assert_rejected_before_side_effects(now.date().isoformat(), past_start)


if __name__ == "__main__":
    unittest.main()
