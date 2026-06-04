import logging
import os
import requests

from datetime import date
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.frankfurter.app"
BASE_CURRENCY = os.getenv("BASE_CURRENCY", "USD")
TARGET_CURRENCIES = os.getenv("TARGET_CURRENCIES", "UZS,RUB,EUR,GBP").split(",")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _get(url: str, params: dict) -> dict:
    """Internal GET request with automatic retry on failure."""
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_latest() -> dict | None:
    """
    Fetch the latest available exchange rates from Frankfurter.
    Returns the raw JSON dict, or None if the request fails.
    """
    url = f"{API_BASE_URL}/latest"
    params = {
        "base": BASE_CURRENCY,
        "symbols": ",".join(TARGET_CURRENCIES),
    }
    try:
        data = _get(url, params)
        logger.info("Fetched latest rates for date: %s", data.get("date"))
        return data
    except Exception as exc:
        logger.error("Failed to fetch latest rates: %s", exc)
        return None


def fetch_for_date(target_date: date) -> dict | None:
    """
    Fetch exchange rates for a specific historical date.
    Returns the raw JSON dict, or None if unavailable (e.g. weekend/holiday).
    """
    date_str = target_date.isoformat()
    url = f"{API_BASE_URL}/{date_str}"
    params = {
        "base": BASE_CURRENCY,
        "symbols": ",".join(TARGET_CURRENCIES),
    }
    try:
        data = _get(url, params)
        logger.info("Fetched rates for date: %s", data.get("date"))
        return data
    except requests.exceptions.HTTPError as exc:
        if exc.response.status_code == 404:
            logger.info("No rates available for %s (weekend or holiday) — skipping.", date_str)
        else:
            logger.error("HTTP error fetching rates for %s: %s", date_str, exc)
        return None
    except Exception as exc:
        logger.error("Failed to fetch rates for %s: %s", date_str, exc)
        return None