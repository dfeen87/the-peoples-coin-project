import threading
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError
from flask import Flask

# Assuming these utilities exist from previous files
from ..db.db_utils import get_session_scope, retry_db_operation
from ..db.models import GoodwillAction

logger = logging.getLogger(__name__)

class AILEEController:
    """
    A multi-threaded background worker controller for processing database tasks.
    Designed to be initialized as a Flask extension.
    """

    def __init__(self):
        """Initializes the controller's state without starting workers."""
        self.app: Flask = None
        self.executor: ThreadPoolExecutor = None
        self._stop_event = threading.Event()
        self._initialized = False
        logger.info("AILEEController instance created.")

    def init_app(self, app: Flask, loop_delay: int = 5, max_workers: int = 2):
        """
        Configures the controller with the Flask app and starts the worker pool.
        This follows the standard Flask extension pattern.

        Args:
            app: The Flask application instance.
            loop_delay: Time in seconds for workers to wait when no tasks are found.
            max_workers: The number of concurrent worker threads to run.
        """
        if self._initialized:
            return
            
        self.app = app
        self.loop_delay = loop_delay
        self.max_workers = max_workers
        
        logger.info("[AILEE] Initializing with %d worker thread(s)...", self.max_workers)
        self.executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix='AILEEWorker'
        )
        self._initialized = True
        self.start()

    def start(self):
        """Submits worker tasks to the thread pool."""
        if not self.executor:
            logger.error("[AILEE] Cannot start, executor not initialized.")
            return

        logger.info("[AILEE] Starting worker pool...")
        self._stop_event.clear()
        for _ in range(self.max_workers):
            self.executor.submit(self._worker_loop)
        logger.info("[AILEE] All worker tasks submitted to the pool.")

    def stop(self):
        """
        Signals worker threads to stop and shuts down the executor gracefully.
        """
        logger.info("[AILEE] Stopping all worker threads...")
        self._stop_event.set()
        if self.executor:
            # The shutdown method handles joining all threads.
            self.executor.shutdown(wait=True, cancel_futures=False)
        logger.info("[AILEE] All worker threads stopped.")

    def _worker_loop(self):
        """
        The main worker loop. Fetches and processes tasks until a stop is signaled.
        """
        thread_name = threading.current_thread().name
        logger.info(f"[{thread_name}] Worker thread started.")

        # The app context is crucial for database sessions and other Flask extensions.
        with self.app.app_context():
            while not self._stop_event.is_set():
                try:
                    processed_count = self._process_goodwill_actions_batch()
                    # If no tasks were processed, wait before polling again.
                    if processed_count == 0:
                        self._stop_event.wait(self.loop_delay)
                except Exception as e:
                    # This catches non-DB errors or DB errors that failed all retries.
                    logger.error(f"[{thread_name}] Unrecoverable error in worker loop: {e}", exc_info=True)
                    # Wait longer after a critical failure to prevent rapid-fire errors.
                    self._stop_event.wait(self.loop_delay * 5)
        
        logger.info(f"[{thread_name}] Worker thread exiting.")

    def _process_goodwill_actions_batch(self) -> int:
        """
        Fetches a batch of pending actions using a database-level lock to prevent
        race conditions between workers.

        Returns:
            The number of actions successfully processed.
        """
        thread_name = threading.current_thread().name

        def db_op_with_locking():
            with get_session_scope() as session:
                # CRITICAL: Use with_for_update(skip_locked=True) to prevent race conditions.
                # This locks the selected rows and tells other workers to ignore them.
                actions = (
                    session.query(GoodwillAction)
                    .filter_by(status='pending')
                    .with_for_update(skip_locked=True)
                    .limit(5)
                    .all()
                )

                if not actions:
                    logger.debug(f"[{thread_name}] No pending GoodwillAction found.")
                    return 0

                logger.info(f"[{thread_name}] Fetched {len(actions)} GoodwillAction(s) for processing.")

                for action in actions:
                    # TODO: Replace with actual business logic for processing the action.
                    # For example: calculate_goodwill(action.contextual_data)
                    time.sleep(0.1)  # Simulate work
                    action.status = 'completed'
                    session.add(action)
                
                # The session commit is handled by the get_session_scope context manager.
                return len(actions)

        try:
            processed_count = retry_db_operation(db_op_with_locking, retries=3, delay=2)
            if processed_count > 0:
                logger.info(f"[{thread_name}] Successfully processed and committed {processed_count} action(s).")
            return processed_count
        except Exception as e:
            logger.error(f"[{thread_name}] Failed to process batch after all retries: {e}", exc_info=True)
            return 0


