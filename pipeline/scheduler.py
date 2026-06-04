import logging
import os
import sys

from datetime import datetime, timezone
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

load_dotenv()

# Allow running from project root: python pipeline/scheduler.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.load_bronze import load_latest, get_latest_bronze_date
from pipeline.transform_silver import run_silver_transform
from pipeline.transform_gold import run_gold_transform

# ── Logging setup ──
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_pipeline() -> None:
    """
    Daily pipeline job — runs at 3:00 AM UTC (8:00 AM UTC+5 Tashkent).

    Steps:
      1. Check if today's data is already in Bronze — skip if so.
      2. Fetch latest rates from Frankfurter → load into Bronze.
      3. Transform Bronze → Silver (clean and validate).
      4. Transform Silver → Gold (metrics and aggregations).
    """
    start_time = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("Pipeline: daily run started at %s UTC.", start_time.strftime("%Y-%m-%d %H:%M:%S"))

    # ── Step 1: Incremental check ──
    latest_date = get_latest_bronze_date()
    today = start_time.strftime("%Y-%m-%d")

    if latest_date and str(latest_date) >= today:
        logger.info(
            "Pipeline: Bronze already has data for %s — skipping fetch.", today
        )
    else:
        # ── Step 2: Bronze ──
        logger.info("Pipeline: fetching latest rates into Bronze ...")
        inserted = load_latest()

        if not inserted:
            logger.warning(
                "Pipeline: no new data inserted into Bronze. "
                "Frankfurter may not have published rates yet "
                "(weekend, holiday, or duplicate). Skipping Silver and Gold."
            )
            return

        logger.info("Pipeline: Bronze loaded successfully.")

        # ── Step 3: Silver ──
        logger.info("Pipeline: running Silver transform ...")
        silver_rows = run_silver_transform()
        logger.info("Pipeline: Silver inserted %d row(s).", silver_rows)

        # ── Step 4: Gold ──
        logger.info("Pipeline: running Gold transform ...")
        run_gold_transform()
        logger.info("Pipeline: Gold transform complete.")

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info("Pipeline: daily run finished in %.1f seconds.", elapsed)
    logger.info("=" * 60)


if __name__ == "__main__":
    logger.info("Scheduler: initializing ...")

    scheduler = BlockingScheduler(timezone="UTC")

    # Run daily at 03:00 UTC = 08:00 Tashkent time (UTC+5)
    scheduler.add_job(
        func=run_pipeline,
        trigger=CronTrigger(hour=3, minute=0, timezone="UTC"),
        id="daily_currency_pipeline",
        name="Daily Currency Exchange Pipeline",
        max_instances=1,        # prevent overlapping runs
        misfire_grace_time=300, # if delayed up to 5 min, still run
    )

    logger.info("Scheduler: job registered — runs daily at 03:00 UTC (08:00 Tashkent).")
    logger.info("Scheduler: press Ctrl+C to stop.")

    try:
        # Run once immediately on startup so you can verify it works
        logger.info("Scheduler: running pipeline once on startup ...")
        run_pipeline()

        # Then hand over to the scheduler for daily runs
        scheduler.start()

    except KeyboardInterrupt:
        logger.info("Scheduler: stopped by user.")
        scheduler.shutdown()