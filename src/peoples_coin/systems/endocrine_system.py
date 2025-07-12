# peoples_coin/peoples_coin/systems/endocrine_system.py

import threading
import logging
import time

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from ..db.db_utils import get_session_scope, retry_db_operation
from ..db.models import GoodwillAction

logger = logging.getLogger(__name__)

class AILEEController:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, app=None, loop_delay=5, max_workers=2):
        """
        Singleton accessor to ensure only one controller instance exists.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(app=app, loop_delay=loop_delay, max_workers=max_workers)
        return cls._instance

    def __init__(self, app=None, loop_delay=5, max_workers=2):
        """
        Initialize controller with optional Flask app context and worker config.
        """
        if not hasattr(self, '_initialized'):
            self.app = app
            self.loop_delay = loop_delay
            self.max_workers = max_workers
            self._stop_event = threading.Event()
            self._worker_threads = []
            self._initialized = True
            logger.info("AILEEController initialized.")

    def start(self):
        """
        Starts the configured number of worker threads.
        """
        logger.info("[AILEE] Starting %d worker thread(s)...", self.max_workers)
        self._stop_event.clear()
        self._worker_threads = []

        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                daemon=True,
                name=f"AILEEWorker-{i+1}"
            )
            self._worker_threads.append(worker)
            worker.start()

        logger.info("[AILEE] All worker threads started.")

    def stop(self):
        """
        Signals worker threads to stop and waits for them to exit gracefully.
        """
        logger.info("[AILEE] Stopping all worker threads...")
        self._stop_event.set()
        for thread in self._worker_threads:
            thread.join(timeout=self.loop_delay + 5)
        logger.info("[AILEE] All worker threads stopped.")

    def _worker_loop(self):
        """
        The main worker loop to process pending GoodwillActions.
        Runs inside Flask app context.
        """
        thread_name = threading.current_thread().name
        logger.info(f"[{thread_name}] Worker thread started.")

        with self.app.app_context():
            while not self._stop_event.is_set():
                try:
                    processed = self._process_goodwill_actions_batch()
                    if processed == 0:
                        # Efficient sleep until next poll or stop signal
                        self._stop_event.wait(self.loop_delay)
                except (OperationalError, StaleDataError) as db_err:
                    logger.warning(f"[{thread_name}] Database error: {db_err}. Rolling back and retrying after delay...")
                    # Rollback session safely using helper
                    with get_session_scope() as session:
                        session.rollback()
                    self._stop_event.wait(self.loop_delay)
                except Exception as e:
                    logger.error(f"[{thread_name}] Unexpected error: {e}", exc_info=True)
                    self._stop_event.wait(self.loop_delay)

        logger.info(f"[{thread_name}] Worker thread exiting.")

    def _process_goodwill_actions_batch(self) -> int:
        """
        Fetches up to 5 pending GoodwillActions, marks them completed.
        Uses retry helper for transient DB errors.

        Returns:
            int: Number of actions processed.
        """
        thread_name = threading.current_thread().name

        def db_op():
            with get_session_scope() as session:
                actions = session.query(GoodwillAction).filter_by(status='pending').limit(5).all()

                if not actions:
                    logger.debug(f"[{thread_name}] No pending GoodwillAction found.")
                    return 0

                logger.info(f"[{thread_name}] Processing {len(actions)} GoodwillAction(s).")

                for action in actions:
                    # TODO: Replace with actual business logic for processing
                    action.status = 'completed'
                    session.add(action)

                # Committing happens automatically when exiting context
                return len(actions)

        try:
            processed_count = retry_db_operation(db_op, retries=3, delay=2)
            if processed_count > 0:
                logger.info(f"[{thread_name}] Committed {processed_count} GoodwillAction(s) as completed.")
            return processed_count
        except Exception as e:
            logger.error(f"[{thread_name}] Failed to process GoodwillActions after retries: {e}", exc_info=True)
            return 0

