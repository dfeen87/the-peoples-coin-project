import logging
import time
import random
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.orm import Session

# Use a relative import, which is more robust within a package structure.
from . import db

logger = logging.getLogger(__name__)


@contextmanager
def get_session_scope():
    """
    Provide a transactional scope for database operations.

    This is the ONLY recommended way to interact with the database. It ensures
    that a block of operations is treated as a single transaction, which is
    either fully committed on success or fully rolled back on failure.

    It works with Flask-SQLAlchemy's managed sessions and does not interfere
    with its lifecycle, making it safe for multi-threaded applications.

    Usage:
        with get_session_scope() as session:
            # Your db operations using the provided session object
            user = UserAccount(...)
            session.add(user)
    """
    try:
        # Yield the managed session object from Flask-SQLAlchemy
        yield db.session
        # If no exceptions were raised, commit the transaction
        db.session.commit()
    except Exception as e:
        # On any exception, log the error and roll back the transaction
        logger.error(f"Database transaction failed. Rolling back. Error: {e}", exc_info=True)
        db.session.rollback()
        # Re-raise the exception to allow higher-level error handlers to catch it
        raise


def retry_db_operation(func, retries=3, delay=1, backoff=2, *args, **kwargs):
    """
    Retry a database operation with exponential backoff and jitter.
    This is useful for transient errors like network issues or deadlocks.

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
                # Add a small random jitter to the delay to prevent thundering herd issues
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

# NOTE: The helper functions `add_and_commit`, `commit_session`, `rollback_session`,
# and `close_session` have been intentionally removed.
#
# REASONING: They encourage unsafe or inefficient database patterns.
# - `add_and_commit` leads to many small, inefficient transactions.
# - The other functions are made obsolete and unsafe by the `get_session_scope`
#   context manager, which handles commit, rollback, and session lifecycle
#   correctly and automatically.
#
# All database code should now exclusively use `get_session_scope` to ensure
# transaction safety and consistency.

