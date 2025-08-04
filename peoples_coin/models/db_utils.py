import logging
import time
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.orm import Session

from peoples_coin.extensions import db  # Centralized SQLAlchemy instance
from peoples_coin.db_types import JSONType, UUIDType, EnumType

logger = logging.getLogger(__name__)


@contextmanager
def get_session_scope():
    """
    Provide a transactional scope for database operations.

    Usage:
        with get_session_scope() as session:
            session.add(...)
            # commit happens automatically unless an exception occurs
    """
    session: Session = db.session
    try:
        yield session
        session.commit()
    except (OperationalError, SQLAlchemyError) as e:
        logger.error(f"Database error during scoped session: {e}", exc_info=True)
        session.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error during scoped session: {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        try:
            session.close()
        except Exception as e:
            logger.error(f"Error closing session: {e}", exc_info=True)


def retry_db_operation(func, retries=3, delay=2, *args, **kwargs):
    """
    Retry a database operation in case of transient failures.
    """
    attempt = 0
    while attempt <= retries:
        try:
            return func(*args, **kwargs)
        except (OperationalError, SQLAlchemyError) as e:
            if attempt == retries:
                logger.error(f"DB operation failed after {retries} retries: {e}", exc_info=True)
                raise
            logger.warning(f"DB operation failed (attempt {attempt+1}/{retries}): {e} — retrying in {delay}s...")
            attempt += 1
            time.sleep(delay)
        except Exception as e:
            logger.error(f"Unexpected error during DB operation: {e}", exc_info=True)
            raise


def add_and_commit(instance):
    """
    Add a model instance to the session and commit the transaction with retries.
    """
    def operation():
        db.session.add(instance)
        db.session.commit()

    retry_db_operation(operation)


def commit_session(session=None):
    """
    Commit the session with retries.
    """
    session = session or db.session

    def operation():
        session.commit()

    retry_db_operation(operation)


def rollback_session(session=None):
    """
    Roll back the session safely.
    """
    session = session or db.session
    try:
        session.rollback()
    except Exception as e:
        logger.error(f"Failed to rollback session: {e}", exc_info=True)


def close_session(session=None):
    """
    Close the session safely.
    """
    session = session or db.session
    try:
        session.close()
    except Exception as e:
        logger.error(f"Failed to close session: {e}", exc_info=True)
