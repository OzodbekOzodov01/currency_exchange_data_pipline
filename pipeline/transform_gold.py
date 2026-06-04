import logging
import os
import psycopg2

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH")


def get_connection():
    """Return a new PostgreSQL connection."""
    return psycopg2.connect(DB_PATH)


def run_gold_transform() -> None:
    """
    Execute the Gold pipeline by calling the PostgreSQL master procedure.
    This runs all three loaders in order:
      1. gold.load_dim_currencies()
      2. gold.load_dim_dates()
      3. gold.load_fct_rates()
    """
    logger.info("Gold: calling run_gold_pipeline() procedure.")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("CALL gold.run_gold_pipeline();")
        conn.commit()
    logger.info("Gold: procedure completed successfully.")