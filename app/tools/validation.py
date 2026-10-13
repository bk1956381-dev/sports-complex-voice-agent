import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo


KARACHI = ZoneInfo("Asia/Karachi")
_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}(?::\d{2})?$")


def parse_booking_window(
    date_value: str,
    start_time_value: str,
    end_time_value: str,
) -> tuple[date, time, time]:
    try:
        booking_date = date.fromisoformat(date_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Date must use YYYY-MM-DD format.") from exc
    if booking_date.isoformat() != date_value:
        raise ValueError("Date must use YYYY-MM-DD format.")

    start_time = _parse_time(start_time_value)
    end_time = _parse_time(end_time_value)
    if end_time <= start_time:
        raise ValueError("End time must be later than start time.")
    if booking_date < datetime.now(KARACHI).date():
        raise ValueError("Bookings cannot be made for a past date.")

    start = datetime.combine(booking_date, start_time, tzinfo=KARACHI)
    if start <= datetime.now(KARACHI):
        raise ValueError("Booking start time must be in the future.")

    return booking_date, start_time, end_time


def validate_facility_hours(
    start_time: time,
    end_time: time,
    opening_time: str,
    closing_time: str,
) -> None:
    opening = time.fromisoformat(opening_time)
    closing = time.fromisoformat(closing_time)
    if start_time < opening or end_time > closing:
        raise ValueError("Requested time is outside facility operating hours.")


def _parse_time(value: str) -> time:
    if not isinstance(value, str) or not _TIME_PATTERN.fullmatch(value):
        raise ValueError("Times must use HH:MM or HH:MM:SS format.")
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Times must use valid 24-hour clock values.") from exc
