import json
import logging
import os
import psycopg2

from datetime import datetime, timezone
from dotenv import load_dotenv
from pipeline.extract import fetch_latest, fetch_for_date
from datetime import date

load_dotenv()

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH")


def get_connection():
    """Return a new PostgreSQL connection."""
    return psycopg2.connect(DB_PATH)


def get_latest_bronze_date() -> str | None:
    """
    Return the most recent fetch_date already stored in raw_rates.
    Used by the scheduler to decide whether today's data needs fetching.
    Returns None if the table is empty.
    """
    sql = "SELECT MAX(fetch_date) FROM bronze.raw_rates;"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            return row[0] if row else None


def _insert_raw(conn, fetch_date: str, raw_json: dict) -> bool:
    """
    Insert one raw API response into raw_rates.
    Returns True if inserted, False if the row already existed (duplicate skip).
    """
    sql = """
        INSERT INTO bronze.raw_rates (fetch_date, base_currency, raw_json, inserted_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (fetch_date, base_currency) DO NOTHING;
    """
    inserted_at = datetime.now(timezone.utc).isoformat()
    base_currency = raw_json.get("base", os.getenv("BASE_CURRENCY", "USD"))

    with conn.cursor() as cur:
        cur.execute(sql, (fetch_date, base_currency, json.dumps(raw_json), inserted_at))
        inserted = cur.rowcount == 1

    if inserted:
        logger.info("Bronze: inserted raw rates for %s.", fetch_date)
    else:
        logger.info("Bronze: row for %s already exists — skipped.", fetch_date)

    return inserted


def load_latest() -> bool:
    """
    Fetch latest rates and write to Bronze.
    Returns True if a new row was inserted.
    """
    data = fetch_latest()
    if data is None:
        logger.warning("Bronze: no data returned from API for latest fetch.")
        return False

    fetch_date = data.get("date")
    with get_connection() as conn:
        inserted = _insert_raw(conn, fetch_date, data)
        conn.commit()
    return inserted


def load_for_date(target_date: date) -> bool:
    """
    Fetch rates for a specific date and write to Bronze.
    Returns True if a new row was inserted.
    """
    data = fetch_for_date(target_date)
    if data is None:
        return False

    fetch_date = data.get("date")
    with get_connection() as conn:
        inserted = _insert_raw(conn, fetch_date, data)
        conn.commit()
    return inserted