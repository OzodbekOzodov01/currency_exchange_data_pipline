import logging
import os
import json
import psycopg2

from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH")


def get_connection():
    """Return a new PostgreSQL connection."""
    return psycopg2.connect(DB_PATH)


def _parse_raw_row(row: tuple) -> list[dict]:
    """
    Parse a single Bronze row into a list of cleaned rate dicts.

    Bronze row order: (fetch_date, base_currency, raw_json, inserted_at)

    Validation rules:
      - exchange_rate must be a positive number (> 0)
      - date and base_currency must not be empty
      - target_currency must not be empty
    """
    fetch_date, base_currency, raw_json_field, inserted_at = row

    # psycopg2 may return JSON column as dict already; handle both cases
    if isinstance(raw_json_field, str):
        try:
            raw_json = json.loads(raw_json_field)
        except json.JSONDecodeError as exc:
            logger.error("Silver: could not parse JSON for fetch_date=%s — %s", fetch_date, exc)
            return []
    else:
        raw_json = raw_json_field

    rates = raw_json.get("rates", {})
    date_str = raw_json.get("date", fetch_date)

    if not date_str or not base_currency:
        logger.warning(
            "Silver: missing date or base_currency for fetch_date=%s — skipping.", fetch_date
        )
        return []

    cleaned = []
    for target_currency, rate in rates.items():
        if not target_currency:
            logger.warning(
                "Silver: empty target_currency in fetch_date=%s — skipping row.", fetch_date
            )
            continue

        try:
            rate = float(rate)
        except (TypeError, ValueError):
            logger.warning(
                "Silver: non-numeric rate for %s/%s on %s — skipping.",
                base_currency, target_currency, date_str,
            )
            continue

        if rate <= 0:
            logger.warning(
                "Silver: invalid rate %.6f for %s/%s on %s — skipping.",
                rate, base_currency, target_currency, date_str,
            )
            continue

        cleaned.append({
            "date": date_str,           # will be cast to DATE in PostgreSQL
            "base_currency": base_currency,
            "target_currency": target_currency,
            "exchange_rate": round(rate, 2),
        })

    logger.debug(
        "Silver: parsed %d valid rate(s) from Bronze row fetch_date=%s.",
        len(cleaned), fetch_date,
    )
    return cleaned


def _get_unprocessed_bronze_rows(conn) -> list[tuple]:
    """
    Return Bronze rows not yet loaded into Silver.
    Compares bronze.fetch_date (varchar) to silver.date (date) via cast.
    """
    sql = """
        SELECT r.fetch_date, r.base_currency, r.raw_json, r.inserted_at
        FROM bronze.raw_rates r
        LEFT JOIN silver.cleaned_rates c
            ON r.fetch_date::date = c.date
            AND r.base_currency = c.base_currency
        WHERE c.date IS NULL
        ORDER BY r.fetch_date ASC;
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def _insert_cleaned_rows(conn, rows: list[dict]) -> int:
    """
    Insert cleaned rows into silver.cleaned_rates.
    Skips duplicates via ON CONFLICT on (date, base_currency, target_currency).
    Returns the number of rows actually inserted.
    """
    if not rows:
        return 0

    sql = """
        INSERT INTO silver.cleaned_rates
            (date, base_currency, target_currency, exchange_rate, load_timestamp)
        VALUES (%s::date, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING;
    """
    load_timestamp = datetime.now(timezone.utc).isoformat()
    inserted = 0

    with conn.cursor() as cur:
        for row in rows:
            cur.execute(sql, (
                row["date"],
                row["base_currency"],
                row["target_currency"],
                row["exchange_rate"],
                load_timestamp,
            ))
            inserted += cur.rowcount

    return inserted


def run_silver_transform() -> int:
    """
    Main entry point for the Silver transformation.
    Reads all unprocessed Bronze rows, validates and parses them,
    and writes cleaned records to silver.cleaned_rates.
    Returns total number of rows inserted.
    """
    logger.info("Silver: starting transformation.")
    total_inserted = 0
    total_skipped = 0

    with get_connection() as conn:
        bronze_rows = _get_unprocessed_bronze_rows(conn)

        if not bronze_rows:
            logger.info("Silver: no new Bronze rows to process.")
            return 0

        logger.info("Silver: found %d unprocessed Bronze row(s).", len(bronze_rows))

        for raw_row in bronze_rows:
            cleaned_rows = _parse_raw_row(raw_row)

            # Count how many rates were in the raw JSON vs how many passed validation
            raw_json_field = raw_row[2]
            if isinstance(raw_json_field, str):
                raw_json = json.loads(raw_json_field)
            else:
                raw_json = raw_json_field
            expected = len(raw_json.get("rates", {}))
            skipped = expected - len(cleaned_rows)
            total_skipped += skipped

            inserted = _insert_cleaned_rows(conn, cleaned_rows)
            total_inserted += inserted

        conn.commit()

    logger.info(
        "Silver: transformation complete. Inserted=%d, Skipped/Invalid=%d.",
        total_inserted, total_skipped,
    )
    return total_inserted