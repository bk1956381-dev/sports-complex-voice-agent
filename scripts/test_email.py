from app.tools.email import send_booking_email


result = send_booking_email(
    customer_email="bk1956381@gmail.com",
    customer_name="Test Customer",
    facility="Tennis Court",
    date="2026-10-06",
    start_time="18:00",
    end_time="19:00",
)

print(result)