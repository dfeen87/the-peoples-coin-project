import logging
import time
import random
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError, OperationalError
from flask_sqlalchemy import SQLAlchemy  # For type hinting

logger = logging.getLogger(__name__)


@contextmanager
def get_session_scope(db_instance: SQLAlchemy):
    """
    Provide a transactional scope for database operations.

    This ensures that a block of operations is treated as a single transaction,
    which is either fully committed on success or fully rolled back on failure.

    Args:
        db_instance (SQLAlchemy): The Flask-SQLAlchemy db instance initialized with the app.

    Usage:
        from your_app.extensions import db
        with get_session_scope(db) as session:
            user = UserAccount(...)
            session.add(user)
    """
    session = db_instance.session
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.error(f"Database transaction failed. Rolling back. Error: {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()


def retry_db_operation(func, retries=3, delay=1, backoff=2, *args, **kwargs):
    """
    Retry a database operation with exponential backoff and jitter.

    Useful for transient errors like network issues or deadlocks.

    Args:
        func (callable): The DB operation function to call.
        retries (int): Number of retry attempts.
        delay (float): Initial seconds to wait between retries.
        backoff (float): Multiplier for the delay after each retry.
        *args: Arguments to pass to func.
        **kwargs: Keyword arguments to pass to func.

    Returns:
        The return value of func on success.
    """
    current_delay = delay
    for attempt in range(retries + 1):
        try:
            return func(*args, **kwargs)
        except (OperationalError, SQLAlchemyError) as e:
            if attempt == retries:
                logger.error(f"DB operation failed after {retries + 1} attempts: {e}", exc_info=True)
                raise
            else:
                jitter = random.uniform(0, 0.1 * current_delay)
                logger.warning(
                    f"DB operation failed on attempt {attempt + 1}/{retries + 1}: {e}. "
                    f"Retrying in {current_delay + jitter:.2f}s..."
                )
                time.sleep(current_delay + jitter)
                current_delay *= backoff
        except Exception as e:
            logger.error(f"Unexpected non-database error during retryable operation: {e}", exc_info=True)
            raise

