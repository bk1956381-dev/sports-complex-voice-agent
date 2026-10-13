from app.tools.calendar import get_calendar_service


service = get_calendar_service()

result = service.calendarList().list().execute()

for calendar in result.get("items", []):
    print("Name:", calendar.get("summary"))
    print("ID:", calendar.get("id"))
    print("-" * 50)