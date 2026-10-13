import os

import mysql.connector
from dotenv import load_dotenv


load_dotenv()

FACILITY_DEFAULTS = (
    ("Tennis Court", 2000, "08:00:00", "23:00:00"),
    ("Football Ground", 5000, "08:00:00", "23:59:59"),
    ("Cricket Ground", 4000, "08:00:00", "23:59:59"),
    ("Padel Court", 2500, "09:00:00", "23:00:00"),
)


def get_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        database=os.getenv("DB_NAME", "sports_complex"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD"),
    )


def initialize_facilities():
    connection = get_connection()
    try:
        cursor = connection.cursor()
        try:
            for name, rate, opening_time, closing_time in FACILITY_DEFAULTS:
                cursor.execute(
                    "SELECT id FROM facilities WHERE name = %s ORDER BY id LIMIT 1 FOR UPDATE",
                    (name,),
                )
                existing = cursor.fetchone()
                if not existing:
                    cursor.execute(
                        """
                        INSERT INTO facilities (name, rate, opening_time, closing_time)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (name, rate, opening_time, closing_time),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()


def get_facility_record(name: str):
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT id, name, rate,
                       CAST(opening_time AS CHAR) AS opening_time,
                       CAST(closing_time AS CHAR) AS closing_time
                FROM facilities
                WHERE name = %s
                ORDER BY id
                LIMIT 1
                """,
                (name,),
            )
            return cursor.fetchone()
        finally:
            cursor.close()
    finally:
        connection.close()