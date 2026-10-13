import asyncio
import socket
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from app.database import FACILITY_DEFAULTS, initialize_facilities
from app.main import app
from app.tools import booking, information
from app.tools.validation import KARACHI


class StartupCursor:
    def __init__(self, facilities):
        self.facilities = facilities
        self.query = ""
        self.params = ()
        self.executed = []

    def execute(self, query, params=()):
        self.query = query
        self.params = params
        self.executed.append((query, params))
        if query.lstrip().upper().startswith("INSERT INTO FACILITIES"):
            name, rate, opening_time, closing_time = params
            self.facilities[name] = {
                "id": len(self.facilities) + 1,
                "rate": rate,
                "opening_time": opening_time,
                "closing_time": closing_time,
            }

    def fetchone(self):
        name = self.params[0]
        row = self.facilities.get(name)
        return (row["id"],) if row else None

    def close(self):
        pass


class StartupConnection:
    def __init__(self, facilities):
        self.cursor_instance = StartupCursor(facilities)
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        raise AssertionError("Unexpected startup rollback.")

    def close(self):
        pass


class BookingCursor:
    def __init__(self, *, overlap=False):
        self.overlap = overlap
        self.query = ""
        self.lastrowid = 71

    def execute(self, query, params=()):
        self.query = " ".join(query.split()).upper()

    def fetchone(self):
        if self.query.startswith("SELECT ID FROM FACILITIES WHERE ID"):
            return {"id": 1}
        if self.query.startswith("SELECT BOOKING_ID FROM BOOKINGS"):
            return {"booking_id": "existing"} if self.overlap else None
        if self.query.startswith("SELECT ID FROM CUSTOMERS"):
            return None
        return None

    def close(self):
        pass


class BookingConnection:
    def __init__(self, *, overlap=False, commit_error=None):
        self.cursor_instance = BookingCursor(overlap=overlap)
        self.commit_error = commit_error
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self, **_kwargs):
        return self.cursor_instance

    def start_transaction(self):
        pass

    def commit(self):
        self.commits += 1
        if self.commit_error:
            raise self.commit_error

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class AvailabilityCursor:
    def __init__(self, *, overlap):
        self.overlap = overlap

    def execute(self, _query, _params=()):
        pass

    def fetchone(self):
        return (1,) if self.overlap else None

    def close(self):
        pass


class AvailabilityConnection:
    def __init__(self, *, overlap):
        self.cursor_instance = AvailabilityCursor(overlap=overlap)
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


class SafeBackendFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_guard = patch(
            "mysql.connector.connect",
            side_effect=AssertionError("Real MySQL connection attempted."),
        )
        def block_network(_socket, _address):
            raise AssertionError("Outbound network connection attempted.")

        cls.network_guard = patch.object(
            socket.socket, "connect", new=block_network
        )
        cls.db_guard.start()
        cls.network_guard.start()

    @classmethod
    def tearDownClass(cls):
        cls.network_guard.stop()
        cls.db_guard.stop()

    def setUp(self):
        self.facility = {
            "id": 1,
            "name": "Tennis Court",
            "rate": 2000,
            "opening_time": "08:00:00",
            "closing_time": "23:00:00",
        }
        self.booking_date = (
            datetime.now(KARACHI).date() + timedelta(days=2)
        ).isoformat()

    def _booking(self):
        return {
            "facility": "tennis",
            "date": self.booking_date,
            "start_time": "10:00",
            "end_time": "11:00",
            "customer_name": "Isolated Test",
            "customer_phone": "00000000",
            "customer_email": "isolated@example.invalid",
        }

    def test_lifespan_preserves_existing_facility_customizations(self):
        facilities = {
            "Tennis Court": {
                "id": 9,
                "rate": 9876,
                "opening_time": "07:15:00",
                "closing_time": "21:45:00",
            }
        }
        connection = StartupConnection(facilities)

        async def enter_and_exit_lifespan():
            async with app.router.lifespan_context(app):
                pass

        with (
            patch("app.database.get_connection", return_value=connection),
            patch(
                "app.main.initialize_facilities",
                wraps=initialize_facilities,
            ) as initialize,
        ):
            self.network_guard.stop()
            try:
                asyncio.run(enter_and_exit_lifespan())
            finally:
                self.network_guard.start()

        initialize.assert_called_once_with()
        self.assertEqual(
            facilities["Tennis Court"],
            {
                "id": 9,
                "rate": 9876,
                "opening_time": "07:15:00",
                "closing_time": "21:45:00",
            },
        )
        self.assertTrue(connection.committed)
        statements = [
            query.upper() for query, _params in connection.cursor_instance.executed
        ]
        self.assertFalse(any("UPDATE FACILITIES" in query for query in statements))
        self.assertEqual(
            set(facilities),
            {facility[0] for facility in FACILITY_DEFAULTS},
        )

    def test_safety_guards_reject_real_db_and_network_access(self):
        import mysql.connector

        with self.assertRaisesRegex(
            AssertionError, "Real MySQL connection attempted"
        ):
            mysql.connector.connect()

        sock = socket.socket()
        try:
            with self.assertRaisesRegex(
                AssertionError, "Outbound network connection attempted"
            ):
                sock.connect(("example.invalid", 443))
        finally:
            sock.close()

    def test_availability_reads_mysql_and_does_not_call_calendar(self):
        for overlap, expected in ((False, True), (True, False)):
            connection = AvailabilityConnection(overlap=overlap)
            with (
                patch(
                    "app.tools.information.get_facility_record",
                    return_value=self.facility,
                ),
                patch(
                    "app.tools.information.get_connection",
                    return_value=connection,
                ),
            ):
                result = information.check_availability(
                    "tennis",
                    self.booking_date,
                    "10:00",
                    "11:00",
                )
            self.assertTrue(result["success"])
            self.assertEqual(result["available"], expected)
            self.assertTrue(connection.closed)

    def test_overlapping_booking_has_no_external_side_effects(self):
        connection = BookingConnection(overlap=True)
        with (
            patch(
                "app.tools.booking.get_facility_record",
                return_value=self.facility,
            ),
            patch("app.tools.booking.get_connection", return_value=connection),
            patch("app.tools.booking.create_calendar_event") as create_event,
            patch("app.tools.booking.send_booking_email") as send_email,
            patch("app.tools.booking._insert_booking") as insert_booking,
        ):
            result = booking.create_booking(**self._booking())

        self.assertFalse(result["success"])
        self.assertFalse(result["booking_confirmed"])
        self.assertFalse(result["booking_persisted"])
        self.assertFalse(result["calendar_event_created"])
        self.assertFalse(result["email_sent"])
        create_event.assert_not_called()
        send_email.assert_not_called()
        insert_booking.assert_not_called()
        self.assertEqual(connection.rollbacks, 1)

    def test_calendar_creation_failure_reports_no_booking(self):
        connection = BookingConnection()
        with (
            patch(
                "app.tools.booking.get_facility_record",
                return_value=self.facility,
            ),
            patch("app.tools.booking.get_connection", return_value=connection),
            patch(
                "app.tools.booking.create_calendar_event",
                side_effect=RuntimeError("Calendar unavailable"),
            ),
            patch("app.tools.booking.send_booking_email") as send_email,
        ):
            result = booking.create_booking(**self._booking())

        self.assertFalse(result["booking_confirmed"])
        self.assertFalse(result["booking_persisted"])
        self.assertIsNone(result["calendar_event_created"])
        self.assertFalse(result["email_sent"])
        send_email.assert_not_called()

    def test_database_insert_failure_rolls_back_and_deletes_calendar_event(self):
        connection = BookingConnection()
        with (
            patch(
                "app.tools.booking.get_facility_record",
                return_value=self.facility,
            ),
            patch("app.tools.booking.get_connection", return_value=connection),
            patch(
                "app.tools.booking.create_calendar_event",
                return_value="mock-event",
            ),
            patch("app.tools.booking.delete_calendar_event") as delete_event,
            patch(
                "app.tools.booking._insert_booking",
                side_effect=RuntimeError("mock insert failure"),
            ),
            patch("app.tools.booking.send_booking_email") as send_email,
        ):
            result = booking.create_booking(**self._booking())

        self.assertFalse(result["booking_confirmed"])
        self.assertFalse(result["booking_persisted"])
        self.assertFalse(result["calendar_event_created"])
        self.assertFalse(result["email_sent"])
        self.assertIsNone(result["calendar_event_id"])
        delete_event.assert_called_once_with("mock-event")
        send_email.assert_not_called()
        self.assertEqual(connection.rollbacks, 1)

    def test_calendar_cleanup_failure_is_reported(self):
        connection = BookingConnection()
        with (
            patch(
                "app.tools.booking.get_facility_record",
                return_value=self.facility,
            ),
            patch("app.tools.booking.get_connection", return_value=connection),
            patch(
                "app.tools.booking.create_calendar_event",
                return_value="orphan-event",
            ),
            patch(
                "app.tools.booking.delete_calendar_event",
                side_effect=RuntimeError("mock delete failure"),
            ),
            patch(
                "app.tools.booking._insert_booking",
                side_effect=RuntimeError("mock insert failure"),
            ),
            patch("app.tools.booking.send_booking_email") as send_email,
        ):
            result = booking.create_booking(**self._booking())

        self.assertFalse(result["booking_persisted"])
        self.assertTrue(result["calendar_event_created"])
        self.assertEqual(result["calendar_event_id"], "orphan-event")
        self.assertFalse(result["email_sent"])
        self.assertIn("cleanup failed", result["message"])
        send_email.assert_not_called()

    def test_commit_failure_reports_persistence_as_unknown(self):
        connection = BookingConnection(commit_error=RuntimeError("commit uncertain"))
        with (
            patch(
                "app.tools.booking.get_facility_record",
                return_value=self.facility,
            ),
            patch("app.tools.booking.get_connection", return_value=connection),
            patch(
                "app.tools.booking.create_calendar_event",
                return_value="mock-event",
            ),
            patch("app.tools.booking.delete_calendar_event") as delete_event,
            patch("app.tools.booking.send_booking_email") as send_email,
        ):
            result = booking.create_booking(**self._booking())

        self.assertIsNone(result["booking_persisted"])
        self.assertFalse(result["booking_confirmed"])
        self.assertFalse(result["calendar_event_created"])
        self.assertFalse(result["email_sent"])
        delete_event.assert_called_once_with("mock-event")
        send_email.assert_not_called()

    def test_email_failure_does_not_mark_booking_as_failed(self):
        connection = BookingConnection()
        email_failure = {"success": False, "message": "SMTP rejected the message."}
        with (
            patch(
                "app.tools.booking.get_facility_record",
                return_value=self.facility,
            ),
            patch("app.tools.booking.get_connection", return_value=connection),
            patch(
                "app.tools.booking.create_calendar_event",
                return_value="mock-event",
            ),
            patch(
                "app.tools.booking._insert_booking",
                return_value="BK-0123456789abcdef",
            ),
            patch(
                "app.tools.booking.send_booking_email",
                return_value=email_failure,
            ),
        ):
            result = booking.create_booking(**self._booking())

        self.assertTrue(result["success"])
        self.assertTrue(result["booking_confirmed"])
        self.assertTrue(result["booking_persisted"])
        self.assertTrue(result["calendar_event_created"])
        self.assertFalse(result["email_sent"])
        self.assertEqual(result["email"], email_failure)
        self.assertIn("email was not sent", result["message"])
        self.assertEqual(connection.commits, 1)

    def test_email_exception_does_not_hide_committed_booking(self):
        connection = BookingConnection()
        with (
            patch(
                "app.tools.booking.get_facility_record",
                return_value=self.facility,
            ),
            patch("app.tools.booking.get_connection", return_value=connection),
            patch(
                "app.tools.booking.create_calendar_event",
                return_value="mock-event",
            ),
            patch(
                "app.tools.booking._insert_booking",
                return_value="BK-0123456789abcdef",
            ),
            patch(
                "app.tools.booking.send_booking_email",
                side_effect=RuntimeError("mock SMTP error"),
            ),
        ):
            result = booking.create_booking(**self._booking())

        self.assertTrue(result["booking_confirmed"])
        self.assertTrue(result["booking_persisted"])
        self.assertFalse(result["email_sent"])
        self.assertEqual(
            result["email"]["message"],
            "Confirmation email could not be sent.",
        )

    def test_database_connection_failure_returns_nonconfirmed_result(self):
        with (
            patch(
                "app.tools.booking.get_facility_record",
                return_value=self.facility,
            ),
            patch(
                "app.tools.booking.get_connection",
                side_effect=RuntimeError("mock DB unavailable"),
            ),
            patch("app.tools.booking.create_calendar_event") as create_event,
            patch("app.tools.booking.send_booking_email") as send_email,
        ):
            result = booking.create_booking(**self._booking())

        self.assertFalse(result["booking_confirmed"])
        self.assertFalse(result["booking_persisted"])
        self.assertFalse(result["calendar_event_created"])
        self.assertFalse(result["email_sent"])
        create_event.assert_not_called()
        send_email.assert_not_called()


if __name__ == "__main__":
    unittest.main()
