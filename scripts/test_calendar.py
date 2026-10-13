from app.tools.calendar import create_calendar_event

event_id = create_calendar_event(
    facility="tennis",
    date="2026-10-09",
    start_time="18:00",
    end_time="19:00",
    customer_name="Test Customer",
    customer_phone="03001234567",
)

print("Calendar event created!")
print("Event ID:", event_id)
