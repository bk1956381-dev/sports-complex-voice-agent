import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


def send_booking_email(
    customer_email: str,
    customer_name: str,
    facility: str,
    date: str,
    start_time: str,
    end_time: str,
):
    sender = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_APP_PASSWORD")

    if not sender or not password:
        return {
            "success": False,
            "message": "Email configuration is missing."
        }

    message = EmailMessage()

    message["Subject"] = "Sports Complex Booking Confirmation"
    message["From"] = sender
    message["To"] = customer_email

    message.set_content(
        f"""Hello {customer_name},

Your sports facility booking has been confirmed.

Facility: {facility}
Date: {date}
Time: {start_time} - {end_time}

Thank you for booking with us.

Sports Complex
"""
    )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.send_message(message)

        return {
            "success": True,
            "message": "Confirmation email sent successfully."
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Email sending failed: {str(e)}"
        }