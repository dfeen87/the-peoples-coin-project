import threading
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from flask import Flask

# Assuming these utilities and models exist from previous files
from ..db.db_utils import get_session_scope, retry_db_operation
from ..db.models import GoodwillAction

logger = logging.getLogger(__name__)

class EndocrineSystem:
    """The Endocrine System. A multi-threaded background worker controller."""

    def __init__(self):
        """Initializes the controller's state."""
        self.app: Optional[Flask] = None
        self.executor: Optional[ThreadPoolExecutor] = None
        self._stop_event = threading.Event()
        self._initialized = False
        logger.info("EndocrineSystem instance created.")

    def init_app(self, app: Flask, loop_delay: int = 5, max_workers: int = 2):
        """Configures the controller with the Flask app but does NOT start it."""
        if self._initialized:
            return
            
        self.app = app
        self.loop_delay = loop_delay
        self.max_workers = max_workers
        
        self.executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix='EndocrineWorker'
        )
        self._initialized = True
        logger.info("[Endocrine] System initialized and ready to start.")
        # NOTE: self.start() is now called explicitly from run.py

    def start(self):
        """Submits worker tasks to the thread pool."""
        if not self.executor:
            logger.error("[Endocrine] Cannot start, executor not initialized.")
            return

        logger.info("[Endocrine] Starting worker pool...")
        self._stop_event.clear()
        for _ in range(self.max_workers):
            self.executor.submit(self._worker_loop)
        logger.info("[Endocrine] All worker tasks submitted to the pool.")

    def stop(self):
        """Signals worker threads to stop and shuts down the executor gracefully."""
        if self.executor:
            logger.info("[Endocrine] Stopping all worker threads...")
            self._stop_event.set()
            self.executor.shutdown(wait=True, cancel_futures=False)
            logger.info("[Endocrine] All worker threads stopped.")

    def is_running(self) -> bool:
        """Checks if the worker threads are active."""
        return self.executor is not None and not self.executor._shutdown

    def _worker_loop(self):
        thread_name = threading.current_thread().name
        logger.info(f"[{thread_name}] Worker thread started.")

        with self.app.app_context():
            while not self._stop_event.is_set():
                try:
                    processed_count = self._process_goodwill_actions_batch()
                    if processed_count == 0:
                        self._stop_event.wait(self.loop_delay)
                except Exception as e:
                    logger.error(f"[{thread_name}] Unrecoverable error in worker loop: {e}", exc_info=True)
                    self._stop_event.wait(self.loop_delay * 5)
        
        logger.info(f"[{thread_name}] Worker thread exiting.")

    def _process_goodwill_actions_batch(self) -> int:
        thread_name = threading.current_thread().name

        def db_op_with_locking():
            with get_session_scope() as session:
                actions = (
                    session.query(GoodwillAction)
                    .filter_by(status='pending')
                    .with_for_update(skip_locked=True)
                    .limit(5)
                    .all()
                )
                if not actions:
                    return 0
                for action in actions:
                    time.sleep(0.1)
                    action.status = 'completed'
                    session.add(action)
                return len(actions)

        try:
            processed_count = retry_db_operation(db_op_with_locking, retries=3, delay=2)
            if processed_count > 0:
                logger.info(f"[{thread_name}] Successfully processed {processed_count} action(s).")
            return processed_count
        except Exception as e:
            logger.error(f"[{thread_name}] Failed to process batch after all retries: {e}", exc_info=True)
            return 0

