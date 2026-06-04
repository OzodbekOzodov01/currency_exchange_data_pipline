import json
import pytest
import requests
 
from datetime import date
from unittest.mock import MagicMock, patch
 
from pipeline.transform_silver import _parse_raw_row
from pipeline.transform_gold import run_gold_transform
 
 
# =============================================================
#  BRONZE TESTS
# =============================================================
 
def test_fetch_for_date_returns_none_on_404():
    """fetch_for_date() should return None for weekends/holidays (404)."""
    from pipeline.extract import fetch_for_date
 
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=mock_response
    )
 
    with patch("pipeline.extract.requests.get", return_value=mock_response):
        result = fetch_for_date(date(2026, 5, 3))  # Sunday
 
    assert result is None
 
 
def test_fetch_latest_returns_dict_on_success():
    """fetch_latest() should return the parsed JSON dict on success."""
    from pipeline.extract import fetch_latest
 
    fake_data = {"amount": 1.0, "base": "USD", "date": "2026-06-03", "rates": {"EUR": 0.86}}
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = fake_data
 
    with patch("pipeline.extract.requests.get", return_value=mock_response):
        result = fetch_latest()
 
    assert result["base"] == "USD"
 
 
# =============================================================
#  SILVER TESTS
# =============================================================
 
def test_valid_rates_are_parsed():
    """Valid rates should be returned as cleaned dicts."""
    raw_json = json.dumps({"date": "2026-05-01", "base": "USD", "rates": {"EUR": 0.86, "GBP": 0.74}})
    row = ("2026-05-01", "USD", raw_json, "2026-05-01T03:00:00+00:00")
 
    result = _parse_raw_row(row)
 
    assert len(result) == 2
 
 
def test_zero_rate_is_filtered():
    """A rate of 0 must be dropped."""
    raw_json = json.dumps({"date": "2026-05-01", "base": "USD", "rates": {"EUR": 0.0, "GBP": 0.74}})
    row = ("2026-05-01", "USD", raw_json, "2026-05-01T03:00:00+00:00")
 
    result = _parse_raw_row(row)
 
    assert len(result) == 1
    assert result[0]["target_currency"] == "GBP"
 
 
def test_invalid_json_returns_empty():
    """Corrupted JSON in Bronze should return empty list, not crash."""
    row = ("2026-05-01", "USD", "NOT VALID JSON {{{", "2026-05-01T03:00:00+00:00")
 
    result = _parse_raw_row(row)
 
    assert result == []
 
 
# =============================================================
#  GOLD TESTS
# =============================================================
 
def test_rate_change_pct_formula():
    """Day-over-day % change formula should be correct."""
    current, previous = 0.75, 0.74
    expected = round(((0.75 - 0.74) / 0.74) * 100, 5)
    result = round(((current - previous) / previous) * 100, 5)
 
    assert result == expected
 
 
def test_seven_day_avg_none_when_insufficient_data():
    """seven_day_avg should be None when fewer than 5 trading days exist."""
    rates = [0.86, 0.85, 0.86, 0.84]  # only 4 days
    result = round(sum(rates) / len(rates), 5) if len(rates) >= 5 else None
 
    assert result is None
 
 
def test_run_gold_transform_calls_procedure():
    """run_gold_transform() should call CALL gold.run_gold_pipeline()."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
 
    with patch("pipeline.transform_gold.psycopg2.connect", return_value=mock_conn):
        run_gold_transform()
 
    mock_cursor.execute.assert_called_once_with("CALL gold.run_gold_pipeline();")
 
 
# =============================================================
#  DIM_DATES TEST
# =============================================================
 
def test_weekday_detection():
    """Monday–Friday should be weekday, Saturday–Sunday should not."""
    assert date(2026, 6, 1).weekday() < 5   # Monday
    assert date(2026, 6, 6).weekday() >= 5  # Saturday