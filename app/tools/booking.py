import logging
import uuid

import mysql.connector

from app.database import get_connection, get_facility_record
from app.tools.calendar import create_calendar_event, delete_calendar_event
from app.tools.email import send_booking_email
from app.tools.facilities import get_facility_name
from app.tools.validation import parse_booking_window, validate_facility_hours


logger = logging.getLogger(__name__)


def create_booking(
    facility: str,
    date: str,
    start_time: str,
    end_time: str,
    customer_name: str,
    customer_phone: str,
    customer_email: str,
):
    facility_key = facility.strip().casefold()
    name = get_facility_name(facility_key)
    try:
        record = get_facility_record(name) if name else None
    except Exception:
        logger.exception("Facility lookup failed while creating a booking.")
        return _booking_failure(
            "Booking could not be confirmed because facility details could not be retrieved."
        )
    if not record:
        return _booking_failure(f"Facility '{facility}' was not found.")

    try:
        booking_date, start, end = parse_booking_window(
            date,
            start_time,
            end_time,
        )
        validate_facility_hours(
            start,
            end,
            record["opening_time"],
            record["closing_time"],
        )
    except ValueError as exc:
        return _booking_failure(str(exc))

    normalized_start = start.strftime("%H:%M:%S")
    normalized_end = end.strftime("%H:%M:%S")
    connection = None
    event_id = None
    calendar_event_created = False
    commit_attempted = False
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        try:
            connection.start_transaction()
            cursor.execute(
                "SELECT id FROM facilities WHERE id = %s FOR UPDATE",
                (record["id"],),
            )
            if cursor.fetchone() is None:
                connection.rollback()
                return _booking_failure(f"Facility '{facility}' was not found.")
            cursor.execute(
                """
                SELECT booking_id
                FROM bookings
                WHERE facility_id = %s
                  AND booking_date = %s
                  AND status = 'confirmed'
                  AND start_time < %s
                  AND end_time > %s
                LIMIT 1
                """,
                (
                    record["id"],
                    booking_date,
                    normalized_end,
                    normalized_start,
                ),
            )
            if cursor.fetchone():
                connection.rollback()
                return _booking_failure(
                    "This time slot is already booked."
                )

            cursor.execute(
                """
                SELECT id
                FROM customers
                WHERE email = %s OR phone = %s
                ORDER BY (email = %s) DESC, id
                LIMIT 1
                FOR UPDATE
                """,
                (customer_email, customer_phone, customer_email),
            )
            customer = cursor.fetchone()
            if customer:
                customer_id = customer["id"]
                cursor.execute(
                    """
                    UPDATE customers
                    SET name = %s, phone = %s, email = %s
                    WHERE id = %s
                    """,
                    (customer_name, customer_phone, customer_email, customer_id),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO customers (name, phone, email)
                    VALUES (%s, %s, %s)
                    """,
                    (customer_name, customer_phone, customer_email),
                )
                customer_id = cursor.lastrowid

            try:
                parse_booking_window(
                    booking_date.isoformat(),
                    normalized_start,
                    normalized_end,
                )
            except ValueError as exc:
                connection.rollback()
                return _booking_failure(str(exc))

            try:
                event_id = create_calendar_event(
                    facility=facility_key,
                    date=booking_date.isoformat(),
                    start_time=start.strftime("%H:%M"),
                    end_time=end.strftime("%H:%M"),
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                )
                if not event_id:
                    raise RuntimeError("Calendar did not return an event ID.")
                calendar_event_created = True
            except Exception:
                logger.exception("Calendar event creation failed.")
                calendar_event_created = None
                connection.rollback()
                return _booking_failure(
                    "Calendar event creation could not be confirmed; booking was not saved.",
                    calendar_event_created=None,
                )

            booking_id = _insert_booking(
                cursor=cursor,
                facility_id=record["id"],
                customer_id=customer_id,
                booking_date=booking_date.isoformat(),
                start_time=normalized_start,
                end_time=normalized_end,
                calendar_event_id=event_id,
            )
            commit_attempted = True
            connection.commit()
        except Exception:
            rollback_succeeded = False
            if connection:
                try:
                    connection.rollback()
                    rollback_succeeded = True
                except Exception:
                    logger.exception("Booking transaction rollback failed.")

            if event_id:
                try:
                    delete_calendar_event(event_id)
                    calendar_event_created = False
                    event_id = None
                except Exception:
                    logger.exception(
                        "Failed to remove Calendar event after booking persistence failed."
                    )

            persisted = None if commit_attempted or not rollback_succeeded else False
            if persisted is None:
                message = (
                    "Booking persistence could not be confirmed. "
                    "Please contact staff before retrying."
                )
            elif calendar_event_created:
                message = (
                    "Booking was not saved, but Calendar cleanup failed. "
                    "Staff review is required."
                )
            else:
                message = "Booking was not saved because of a database error."
            logger.exception("Booking persistence failed.")
            return _booking_failure(
                message,
                booking_persisted=persisted,
                calendar_event_created=calendar_event_created,
                calendar_event_id=event_id,
            )
        finally:
            try:
                cursor.close()
            except Exception:
                logger.exception("Booking database cursor could not be closed.")
    except Exception:
        logger.exception("Could not start or complete booking transaction.")
        return _booking_failure(
            (
                "Booking persistence could not be confirmed. "
                "Please contact staff before retrying."
                if commit_attempted
                else "Booking could not be confirmed because the database is unavailable."
            ),
            booking_persisted=None if commit_attempted else False,
            calendar_event_created=calendar_event_created,
            calendar_event_id=event_id,
        )
    finally:
        if connection:
            try:
                connection.close()
            except Exception:
                logger.exception("Booking database connection could not be closed.")

    booking = {
        "booking_id": booking_id,
        "facility": facility_key,
        "date": booking_date.isoformat(),
        "start_time": start.strftime("%H:%M"),
        "end_time": end.strftime("%H:%M"),
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "customer_email": customer_email,
        "status": "confirmed",
    }
    try:
        email_result = send_booking_email(
            customer_email=customer_email,
            customer_name=customer_name,
            facility=record["name"],
            date=booking_date.isoformat(),
            start_time=start.strftime("%H:%M"),
            end_time=end.strftime("%H:%M"),
        )
    except Exception:
        logger.exception("Booking was persisted but confirmation email failed.")
        email_result = {
            "success": False,
            "message": "Confirmation email could not be sent.",
        }
    email_sent = bool(email_result.get("success"))

    return {
        "success": True,
        "message": (
            "Booking confirmed."
            if email_sent
            else "Booking confirmed, but the confirmation email was not sent."
        ),
        "booking_confirmed": True,
        "booking_persisted": True,
        "calendar_event_created": True,
        "booking": booking,
        "calendar_event_id": event_id,
        "email_sent": email_sent,
        "email": email_result,
    }


def _booking_failure(
    message: str,
    *,
    booking_persisted: bool | None = False,
    calendar_event_created: bool | None = False,
    calendar_event_id: str | None = None,
):
    return {
        "success": False,
        "message": message,
        "booking_confirmed": False,
        "booking_persisted": booking_persisted,
        "calendar_event_created": calendar_event_created,
        "calendar_event_id": calendar_event_id,
        "email_sent": False,
    }


def _insert_booking(
    cursor,
    facility_id: int,
    customer_id: int,
    booking_date: str,
    start_time: str,
    end_time: str,
    calendar_event_id: str,
) -> str:
    for _ in range(5):
        booking_id = f"BK-{uuid.uuid4().hex[:16]}"
        try:
            cursor.execute(
                """
                INSERT INTO bookings (
                    booking_id, facility_id, customer_id, booking_date,
                    start_time, end_time, status, calendar_event_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'confirmed', %s)
                """,
                (
                    booking_id,
                    facility_id,
                    customer_id,
                    booking_date,
                    start_time,
                    end_time,
                    calendar_event_id,
                ),
            )
            return booking_id
        except mysql.connector.IntegrityError as exc:
            if exc.errno != 1062:
                raise
    raise RuntimeError("Could not generate a unique booking ID after five attempts.")
