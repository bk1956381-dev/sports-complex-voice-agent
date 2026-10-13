import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from app.database import get_connection, initialize_facilities
from app.tools.booking import create_booking
from app.tools.information import check_availability, get_rate
from app.tools.validation import KARACHI, parse_booking_window


class MySQLIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_facilities()

    def setUp(self):
        token = uuid.uuid4().hex
        self.email = f"mysql-test-{token}@example.invalid"
        self.phone = f"test-{token[:20]}"
        self.booking_date = (
            datetime.now(KARACHI).date() + timedelta(days=2000 + int(token[:4], 16))
        ).isoformat()

    def tearDown(self):
        connection = get_connection()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    DELETE FROM bookings
                    WHERE customer_id IN (
                        SELECT id FROM customers WHERE email = %s OR phone = %s
                    )
                    """,
                    (self.email, self.phone),
                )
                cursor.execute(
                    "DELETE FROM customers WHERE email = %s OR phone = %s",
                    (self.email, self.phone),
                )
                connection.commit()
            finally:
                cursor.close()
        finally:
            connection.close()

    def _create_booking(self, **overrides):
        values = {
            "facility": "tennis",
            "date": self.booking_date,
            "start_time": "10:00",
            "end_time": "11:00",
            "customer_name": "MySQL Integration Test",
            "customer_phone": self.phone,
            "customer_email": self.email,
        }
        values.update(overrides)
        return create_booking(**values)

    def test_database_connection(self):
        connection = get_connection()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute("SELECT DATABASE()")
                self.assertEqual(cursor.fetchone()[0], "sports_complex")
            finally:
                cursor.close()
        finally:
            connection.close()

    def test_facility_lookup_and_rate(self):
        result = get_rate("tennis")
        self.assertTrue(result["success"])
        self.assertEqual(result["facility"], "Tennis Court")
        self.assertEqual(float(result["rate"]), 2000.0)

    def test_availability(self):
        result = check_availability(
            "tennis",
            self.booking_date,
            "10:00",
            "11:00",
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["available"])

    def test_invalid_date_time_and_facility_hours_are_rejected(self):
        invalid_date = check_availability("tennis", "not-a-date", "10:00", "11:00")
        invalid_order = check_availability(
            "tennis",
            self.booking_date,
            "11:00",
            "10:00",
        )
        outside_hours = check_availability(
            "tennis",
            self.booking_date,
            "07:00",
            "08:00",
        )
        self.assertFalse(invalid_date["success"])
        self.assertFalse(invalid_order["success"])
        self.assertFalse(outside_hours["success"])

    def test_overlapping_booking_is_rejected(self):
        with (
            patch("app.tools.booking.create_calendar_event", return_value="test-event"),
            patch("app.tools.booking.send_booking_email", return_value={"success": True}),
        ):
            first = self._create_booking()
            overlap = self._create_booking(
                start_time="10:30",
                end_time="11:30",
            )
        self.assertTrue(first["success"])
        self.assertFalse(overlap["success"])
        self.assertEqual(overlap["message"], "This time slot is already booked.")

    def test_successful_booking(self):
        with (
            patch(
                "app.tools.booking.create_calendar_event",
                return_value="test-event-success",
            ) as create_event,
            patch(
                "app.tools.booking.send_booking_email",
                return_value={"success": True},
            ),
        ):
            result = self._create_booking()
        self.assertTrue(result["success"])
        self.assertEqual(result["booking"]["status"], "confirmed")
        self.assertRegex(result["booking"]["booking_id"], r"^BK-[0-9a-f]{16}$")
        self.assertEqual(
            create_event.call_args.kwargs["date"],
            self.booking_date,
        )

    def test_adjacent_bookings_reuse_customer(self):
        with (
            patch(
                "app.tools.booking.create_calendar_event",
                side_effect=("test-event-one", "test-event-two"),
            ),
            patch(
                "app.tools.booking.send_booking_email",
                return_value={"success": True},
            ),
        ):
            first = self._create_booking()
            second = self._create_booking(
                start_time="11:00",
                end_time="12:00",
            )

        self.assertTrue(first["success"])
        self.assertTrue(second["success"])
        connection = get_connection()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    "SELECT COUNT(*) FROM customers WHERE email = %s",
                    (self.email,),
                )
                self.assertEqual(cursor.fetchone()[0], 1)
            finally:
                cursor.close()
        finally:
            connection.close()

    def test_database_persistence(self):
        with (
            patch(
                "app.tools.booking.create_calendar_event",
                return_value="test-event-persisted",
            ),
            patch(
                "app.tools.booking.send_booking_email",
                return_value={"success": True},
            ),
        ):
            result = self._create_booking()

        connection = get_connection()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    SELECT b.status, b.calendar_event_id, c.email, f.name
                    FROM bookings AS b
                    JOIN customers AS c ON c.id = b.customer_id
                    JOIN facilities AS f ON f.id = b.facility_id
                    WHERE b.booking_id = %s
                    """,
                    (result["booking"]["booking_id"],),
                )
                row = cursor.fetchone()
            finally:
                cursor.close()
        finally:
            connection.close()

        self.assertEqual(
            row,
            ("confirmed", "test-event-persisted", self.email, "Tennis Court"),
        )

    def test_calendar_failure_does_not_confirm_or_persist(self):
        with (
            patch(
                "app.tools.booking.create_calendar_event",
                side_effect=RuntimeError("Calendar unavailable"),
            ),
            patch("app.tools.booking.send_booking_email") as send_email,
        ):
            result = self._create_booking()

        self.assertFalse(result["success"])
        send_email.assert_not_called()
        connection = get_connection()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    "SELECT COUNT(*) FROM customers WHERE email = %s",
                    (self.email,),
                )
                self.assertEqual(cursor.fetchone()[0], 0)
            finally:
                cursor.close()
        finally:
            connection.close()

    def test_start_time_that_becomes_past_before_calendar_is_rejected(self):
        calls = 0

        def become_past(date_value, start_time_value, end_time_value):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("Booking start time must be in the future.")
            return parse_booking_window(date_value, start_time_value, end_time_value)

        with (
            patch("app.tools.booking.parse_booking_window", side_effect=become_past),
            patch("app.tools.booking.create_calendar_event") as create_event,
            patch("app.tools.booking.send_booking_email") as send_email,
        ):
            result = self._create_booking()

        self.assertFalse(result["success"])
        self.assertEqual(
            result["message"],
            "Booking start time must be in the future.",
        )
        create_event.assert_not_called()
        send_email.assert_not_called()

        connection = get_connection()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    "SELECT COUNT(*) FROM customers WHERE email = %s",
                    (self.email,),
                )
                self.assertEqual(cursor.fetchone()[0], 0)
            finally:
                cursor.close()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
