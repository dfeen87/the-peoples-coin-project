import os
import sys
import argparse
import logging
import traceback

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError, OperationalError

from peoples_coin.extensions import db
from peoples_coin.db_types import JSONType, UUIDType, EnumType

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Full production schema SQL (matches your July 25, 2025 final version)
SCHEMA_SQL_PATH = os.path.join(
    os.path.dirname(__file__), "final_production_schema.sql"
)


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def run_schema_sql(engine):
    """
    Executes your full production schema SQL so that enums,
    triggers, functions match production exactly.
    """
    if not os.path.exists(SCHEMA_SQL_PATH):
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_SQL_PATH}")

    with open(SCHEMA_SQL_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    with engine.begin() as conn:
        conn.execute(text(schema_sql))


def init_db(drop: bool = False) -> int:
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@localhost:5432/peoples_coin",
    )

    if not db_url.startswith("postgresql"):
        logger.warning(
            "⚠️ DATABASE_URL is not PostgreSQL — schema behavior may differ from production."
        )

    logger.info(f"Using database URL: {db_url}")

    try:
        engine = create_engine(db_url)

        # Test connection
        logger.info("Testing database connection...")
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✅ Database connection successful.")

        if drop:
            logger.warning("⚠️ Dropping all tables...")
            db.Model.metadata.drop_all(engine)

        # Run SQLAlchemy create_all to create mapped models
        db.Model.metadata.create_all(engine)

        # Then run raw SQL to ensure enums, triggers, etc. match production exactly
        logger.info("Running production schema SQL...")
        run_schema_sql(engine)

        # Show tables
        insp = inspect(engine)
        tables = insp.get_table_names()
        logger.info(f"Tables in database: {tables or 'None'}")

        return 0

    except OperationalError as e:
        logger.error(f"🚨 Operational error: {e}")
        logger.debug(traceback.format_exc())
        return 2
    except SQLAlchemyError as e:
        logger.error(f"❌ SQLAlchemy error: {e}")
        logger.debug(traceback.format_exc())
        return 3
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        logger.debug(traceback.format_exc())
        return 4


def main():
    parser = argparse.ArgumentParser(description="Initialize the database.")
    parser.add_argument(
        "--drop", action="store_true", help="Drop all tables before creating them"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    setup_logging(args.verbose)

    exit_code = init_db(drop=args.drop)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
