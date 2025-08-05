import os
import sys
import argparse
import logging
import traceback

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError, OperationalError

from peoples_coin.factory import create_app
from peoples_coin.extensions import db

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Path to production schema SQL
SCHEMA_SQL_PATH = os.path.join(
    os.path.dirname(__file__), "final_production_schema.sql"
)

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool):
    """Configure logging for console output."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def run_schema_sql(engine):
    """
    Executes full production schema SQL so enums, triggers,
    and functions match production exactly.
    """
    if not os.path.exists(SCHEMA_SQL_PATH):
        logger.error(f"❌ Schema file not found: {SCHEMA_SQL_PATH}")
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_SQL_PATH}")

    logger.info(f"📜 Running schema from: {SCHEMA_SQL_PATH}")
    with open(SCHEMA_SQL_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    with engine.begin() as conn:
        conn.execute(text(schema_sql))


def get_database_url():
    """
    Always use the same logic as in factory.py so Cloud Run + local dev work identically.
    """
    if os.environ.get("K_SERVICE"):
        # Running in Cloud Run
        db_user = os.environ.get("DB_USER")
        db_pass = os.environ.get("DB_PASS")
        db_name = os.environ.get("DB_NAME")
        instance_connection_name = os.environ.get("INSTANCE_CONNECTION_NAME")

        if not all([db_user, db_pass, db_name, instance_connection_name]):
            raise ValueError("Missing required Cloud SQL configuration in environment variables.")

        return (
            f"postgresql+psycopg2://{db_user}:{db_pass}@/{db_name}"
            f"?host=/cloudsql/{instance_connection_name}"
        )

    # Local development
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL is not set for local development.")
    return db_url


def init_db(drop: bool = False) -> int:
    """
    Initialize the database by creating tables and running production schema SQL.
    """
    try:
        database_url = get_database_url()
        logger.info(f"🔗 Using database URL: {database_url}")

        # Create Flask app context so db.Model knows about all models
        app = create_app()

        with app.app_context():
            engine = create_engine(database_url)

            # Test DB connection
            logger.info("🔍 Testing database connection...")
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("✅ Database connection successful.")

            if drop:
                logger.warning("⚠️ Dropping all tables...")
                db.drop_all(bind=engine)

            logger.info("🛠 Creating all mapped tables from SQLAlchemy models...")
            db.create_all(bind=engine)

            logger.info("📜 Applying production schema SQL...")
            run_schema_sql(engine)

            # Show all tables for confirmation
            insp = inspect(engine)
            tables = insp.get_table_names()
            logger.info(f"📂 Tables in database: {tables or 'None'}")

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

