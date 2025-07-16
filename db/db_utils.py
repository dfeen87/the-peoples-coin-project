import logging
import time
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.orm import Session

from peoples_coin.db import db  # Your existing SQLAlchemy db instance

logger = logging.getLogger(__name__)


@contextmanager
def get_session_scope():
    """
    Provide a transactional scope for database operations.

    Usage:
        with get_session_scope() as session:
            # your db operations using session
            session.add(...)
            session.commit()

    Rolls back on exceptions and closes session automatically.
    """
    session: Session = db.session
    try:
        yield session
        session.commit()
    except OperationalError as oe:
        logger.error(f"OperationalError during DB operation: {oe}", exc_info=True)
        session.rollback()
        raise
    except SQLAlchemyError as e:
        logger.error(f"SQLAlchemyError during DB operation: {e}", exc_info=True)
        session.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error during DB operation: {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()


def retry_db_operation(func, retries=3, delay=2, *args, **kwargs):
    """
    Retry a database operation in case of transient failures.

    Args:
        func (callable): The DB operation function to call.
        retries (int): Number of retry attempts before raising exception.
        delay (int | float): Seconds to wait between retries.
        *args: Arguments to pass to func.
        **kwargs: Keyword arguments to pass to func.

    Returns:
        Any: The return value of func on success.

    Raises:
        Exception: Propagates the exception if all retries fail.
    """
    attempt = 0
    while attempt <= retries:
        try:
            return func(*args, **kwargs)
        except (OperationalError, SQLAlchemyError) as e:
            if attempt == retries:
                logger.error(f"DB operation failed after {retries} retries: {e}", exc_info=True)
                raise
            else:
                logger.warning(f"DB operation failed on attempt {attempt+1}/{retries}: {e}. Retrying in {delay}s...")
                attempt += 1
                time.sleep(delay)
        except Exception as e:
            # For unexpected exceptions, log and raise immediately
            logger.error(f"Unexpected error during DB operation: {e}", exc_info=True)
            raise


def add_and_commit(instance):
    """
    Add a model instance to the session and commit the transaction with retries.

    Args:
        instance (db.Model): SQLAlchemy model instance to add and commit.

    Raises:
        Exception: If commit fails after retries.
    """
    def operation():
        db.session.add(instance)
        db.session.commit()

    retry_db_operation(operation)


def commit_session(session=None):
    """
    Commit the session with retries.

    Args:
        session (Session, optional): SQLAlchemy session. Defaults to db.session.

    Raises:
        Exception: If commit fails after retries.
    """
    if session is None:
        session = db.session

    def operation():
        session.commit()

    retry_db_operation(operation)


def rollback_session(session=None):
    """
    Roll back the session safely.

    Args:
        session (Session, optional): SQLAlchemy session. Defaults to db.session.
    """
    if session is None:
        session = db.session
    try:
        session.rollback()
    except Exception as e:
        logger.error(f"Failed to rollback session: {e}", exc_info=True)


def close_session(session=None):
    """
    Close the session safely.

    Args:
        session (Session, optional): SQLAlchemy session. Defaults to db.session.
    """
    if session is None:
        session = db.session
    try:
        session.close()
    except Exception as e:
        logger.error(f"Failed to close session: {e}", exc_info=True)
