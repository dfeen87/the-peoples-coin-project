import os
import sys
import argparse
import logging
import traceback

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError, OperationalError

# Import Base and db from your package's db module
from peoples_coin.extensions import db

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional


logger = logging.getLogger(__name__)


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def init_db(drop: bool = False) -> int:
    """
    Initialize the database: create all tables, optionally drop existing tables.

    Args:
        drop (bool): If True, drop all tables before creating.

    Returns:
        int: Exit code (0=success, >0=failure)
    """
    db_url = os.getenv('DATABASE_URL', 'sqlite:///instance/peoples_coin.db')
    logger.info(f"Using database URL: {db_url}")

    # Ensure SQLite folder exists if needed
    if db_url.startswith('sqlite:///'):
        db_path = db_url.replace('sqlite:///', '', 1)
        folder = os.path.dirname(db_path)
        if folder and not os.path.exists(folder):
            logger.info(f"Creating missing folder: {folder}")
            os.makedirs(folder, exist_ok=True)

    try:
        engine = create_engine(db_url)

        # Test connection
        logger.info("Testing database connection...")
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successful.")

        if drop:
            logger.warning("⚠️ Dropping all tables...")
            Base.metadata.drop_all(engine)

        Base.metadata.create_all(engine)
        logger.info("✅ Database tables created successfully.")

        # Report tables created
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
    parser.add_argument('--drop', action='store_true', help="Drop all tables before creating them")
    parser.add_argument('--verbose', action='store_true', help="Enable debug logging")
    args = parser.parse_args()

    setup_logging(args.verbose)

    exit_code = init_db(drop=args.drop)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

