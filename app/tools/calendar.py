import os
import google_auth_httplib2
import httplib2
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from app.config import GOOGLE_CALENDAR_ID

SCOPES = ["https://www.googleapis.com/auth/calendar"]
KARACHI = ZoneInfo("Asia/Karachi")

TOKEN_FILE = "credentials/token.json"
CLIENT_FILE = "credentials/client_secret.json"


def get_calendar_service():
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES,
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_FILE,
                SCOPES,
            )
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    http = httplib2.Http(timeout=30)

    authorized_http = google_auth_httplib2.AuthorizedHttp(
        creds,
        http=http,
    )

    return build(
        "calendar",
        "v3",
        http=authorized_http,
        cache_discovery=False,
    )


def create_calendar_event(
    facility: str,
    date: str,
    start_time: str,
    end_time: str,
    customer_name: str,
    customer_phone: str,
):
    service = get_calendar_service()
    start = datetime.fromisoformat(f"{date}T{start_time}").replace(tzinfo=KARACHI)
    end = datetime.fromisoformat(f"{date}T{end_time}").replace(tzinfo=KARACHI)

    event = {
        "summary": f"{facility.title()} Booking - {customer_name}",
        "description": (
            f"Customer: {customer_name}\n"
            f"Phone: {customer_phone}"
        ),
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": "Asia/Karachi",
        },
        "end": {
            "dateTime": end.isoformat(),
            "timeZone": "Asia/Karachi",
        },
    }

    result = (
        service.events()
        .insert(
            calendarId=GOOGLE_CALENDAR_ID,
            body=event,
        )
        .execute()
    )

    return result.get("id")


def delete_calendar_event(event_id: str):
    service = get_calendar_service()
    (
        service.events()
        .delete(
            calendarId=GOOGLE_CALENDAR_ID,
            eventId=event_id,
        )
        .execute()
    )