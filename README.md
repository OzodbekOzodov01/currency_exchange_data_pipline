# Currency Exchange Data Pipeline

A production-ready data pipeline that fetches daily currency exchange rates from the [Frankfurter API](https://frankfurter.dev/) and loads them into a PostgreSQL data warehouse following **Medallion architecture** (Bronze → Silver → Gold).

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Running the Pipeline](#running-the-pipeline)
- [Historical Backfill](#historical-backfill)
- [Running Tests](#running-tests)
- [Scheduling](#scheduling)
- [Data Model](#data-model)

---

## Architecture Overview

```
Frankfurter API
      │
      ▼
┌─────────────┐
│   BRONZE    │  Raw JSON responses stored as-is in bronze.raw_rates
│  (Extract)  │  Immutable audit log — never modified after insert
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   SILVER    │  Parsed, validated, deduplicated rows in silver.cleaned_rates
│ (Transform) │  Invalid rates (≤ 0), nulls, and duplicates are removed
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    GOLD     │  Business-ready metrics in gold.fct_aggregated_rates
│  (Enrich)   │  Day-over-day % change, 7-day rolling average
│             │  Star schema with dim_currencies and dim_dates
└─────────────┘
```

**Currencies tracked:** USD (base), EUR, GBP

**Schedule:** Daily at 08:00 Tashkent time (03:00 UTC)

---

## Project Structure

```
currency_exchange_data_pipeline/
├── README.md
├── .env                        # Your local secrets (git-ignored)
├── .env.example                # Template — copy this to .env
├── requirements.txt            # Python dependencies
├── pipeline/
│   ├── __init__.py
│   ├── extract.py              # Frankfurter API calls with retry logic
│   ├── load_bronze.py          # Write raw JSON to Bronze layer
│   ├── transform_silver.py     # Clean and validate → Silver layer
│   ├── transform_gold.py       # Call PostgreSQL Gold procedures
│   └── scheduler.py            # APScheduler daily job
├── sql/
│   ├── schema.sql              # Table definitions for all three layers
│   └── gold_layer.sql          # Stored procedures for Gold layer
└── tests/
    ├── __init__.py
    └── test_transformations.py # Unit tests
```

---

## Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Git

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/OzodbekOzodov01/currency_exchange_data_pipline.git
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```env
DB_PATH=postgresql://postgres:*****@localhost:5432/dwh_currency_exchange
BASE_CURRENCY=USD
TARGET_CURRENCIES=EUR,GBP
LOG_LEVEL=INFO
```

### 4. Create the database

```bash
psql -U postgres -c "CREATE DATABASE dwh_currency_exchange;"
```

### 5. Create the schema

Run the following files in DBeaver or psql in this order:

```bash
psql -U postgres -d dwh_currency_exchange -f sql/schema.sql
psql -U postgres -d dwh_currency_exchange -f sql/gold_procedures.sql
```

---

## Running the Pipeline

### Run each layer individually

```bash
# Bronze — fetch and store latest rates
python -c "
import logging; logging.basicConfig(level=logging.INFO)
from pipeline.load_bronze import load_latest
load_latest()
"

# Silver — clean and validate
python -c "
import logging; logging.basicConfig(level=logging.INFO)
from pipeline.transform_silver import run_silver_transform
run_silver_transform()
"

# Gold — compute metrics
python -c "
import logging; logging.basicConfig(level=logging.INFO)
from pipeline.transform_gold import run_gold_transform
run_gold_transform()
"
```

### Run the full pipeline once

```bash
python pipeline/scheduler.py
```

This runs the full pipeline immediately on startup, then waits for the next scheduled run at 03:00 UTC.
---

## Running Tests

```bash
pytest tests/ -v
```

Tests cover:
- Bronze: API 404 handling, successful fetch
- Silver: valid rate parsing, zero rate filtering, corrupted JSON handling
- Gold: rate change formula, 7-day average threshold, procedure call verification
- Dim dates: weekday detection

---

## Scheduling

The pipeline uses **APScheduler** with a `BlockingScheduler` and a `CronTrigger`.

- **Schedule:** Every day at `03:00 UTC` (equivalent to `08:00 Tashkent time, UTC+5`)
- **Incremental logic:** Checks the latest date in Bronze before fetching — skips if today's data already exists
- **Non-trading days:** If Frankfurter returns no data (weekend or holiday), the pipeline logs the skip and exits cleanly without running Silver or Gold

To start the scheduler:

```bash
python pipeline/scheduler.py
```

Keep the terminal open to maintain the schedule. Press `Ctrl+C` to stop.

---

## Data Model

### Bronze — `bronze.raw_rates`

| Column | Type | Description |
|---|---|---|
| fetch_date | varchar | Date the data was fetched |
| base_currency | varchar | Base currency (always USD) |
| raw_json | varchar | Full API response as JSON string |
| inserted_at | varchar | UTC timestamp of insertion |

### Silver — `silver.cleaned_rates`

| Column | Type | Description |
|---|---|---|
| id | bigint | Auto-incrementing primary key |
| date | date | Rate date |
| base_currency | char(3) | Base currency |
| target_currency | varchar | Target currency code |
| exchange_rate | decimal | Validated rate (always > 0) |
| load_timestamp | timestamptz | UTC timestamp of load |

### Gold — `gold.fct_aggregated_rates`

| Column | Type | Description |
|---|---|---|
| id | bigint | Auto-incrementing primary key |
| date | date | Rate date (FK → dim_dates) |
| base_currency | char(3) | Base currency |
| target_currency | char(3) | Target currency (FK → dim_currencies) |
| exchange_rate | decimal | Exchange rate |
| rate_change_pct | decimal | Day-over-day % change (NULL for first day) |
| seven_day_avg | decimal | 7-day rolling average (NULL if < 5 trading days) |
| load_timestamp | timestamptz | UTC timestamp of load |

### Gold — `gold.dim_currencies`

| Column | Type | Description |
|---|---|---|
| currency_code | char(3) | ISO 4217 code (PK) |
| currenct_name | varchar | Full currency name |
| symbol | char(1) | Currency symbol |
| country | varchar | Issuing country |

### Gold — `gold.dim_dates`

| Column | Type | Description |
|---|---|---|
| date_id | date | The date (PK) |
| date_day | int | Day of month |
| date_month | int | Month number |
| date_year | int | Year |
| is_weekday | boolean | True if Monday–Friday |

---
## Author 
Ozodbek Ozodov
