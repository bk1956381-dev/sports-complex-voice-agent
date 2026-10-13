from app.database import get_connection, get_facility_record
from app.tools.facilities import get_facility_name
from app.tools.validation import parse_booking_window, validate_facility_hours


def general_information():
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT name, rate,
                       TIME_FORMAT(opening_time, '%H:%i:%s') AS opening_time,
                       TIME_FORMAT(closing_time, '%H:%i:%s') AS closing_time
                FROM facilities
                ORDER BY id
                """
            )
            return cursor.fetchall()
        finally:
            cursor.close()
    finally:
        connection.close()


def get_rate(facility: str):
    name = get_facility_name(facility)
    record = get_facility_record(name) if name else None
    if not record:
        return {
            "success": False,
            "message": f"Facility '{facility}' was not found.",
        }

    return {
        "success": True,
        "facility": record["name"],
        "rate": record["rate"],
    }


def check_availability(
    facility: str,
    date: str,
    start_time: str,
    end_time: str,
):
    name = get_facility_name(facility)
    record = get_facility_record(name) if name else None
    if not record:
        return {
            "success": False,
            "message": f"Facility '{facility}' was not found.",
        }

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
        return {"success": False, "message": str(exc)}

    connection = get_connection()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                SELECT 1
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
                    end.strftime("%H:%M:%S"),
                    start.strftime("%H:%M:%S"),
                ),
            )
            is_available = cursor.fetchone() is None
        finally:
            cursor.close()
    finally:
        connection.close()

    result = {
        "success": True,
        "available": is_available,
        "facility": record["name"],
        "date": booking_date.isoformat(),
        "start_time": start.strftime("%H:%M"),
        "end_time": end.strftime("%H:%M"),
    }
    if is_available:
        result["rate"] = record["rate"]
    else:
        result["message"] = "This time slot is already booked."
    return result
