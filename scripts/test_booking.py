from app.tools.booking import create_booking


result = create_booking(
    facility="tennis",
    date="2026-10-09",
    start_time="16:00",
    end_time="19:00",
    customer_name="Test Customer",
    customer_phone="03001234567",
    customer_email="bk1956381@gmail.com",
)


print("Booking result:")
print(result)


