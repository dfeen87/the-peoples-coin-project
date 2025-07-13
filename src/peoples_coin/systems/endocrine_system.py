
import threading
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from flask import Flask

from ..extensions import db
from ..db.db_utils import get_session_scope, retry_db_operation
from ..db.models import GoodwillAction
from ..ai_processor.processor import process_goodwill_action_with_ailee_and_love

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
        logger.info(f"[Endocrine] System initialized with {self.max_workers} workers and loop delay {self.loop_delay}s. Ready to start.")
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

        # Each worker thread uses the app context
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
        processed_count = 0

        def db_op_fetch_and_process():
            with get_session_scope(db) as session:
                actions = (
                    session.query(GoodwillAction)
                    .filter_by(status='pending')
                    # .with_for_update(skip_locked=True) # uncomment if DB supports
                    .limit(self.app.config.get("AILEE_BATCH_SIZE", 5))
                    .all()
                )
                
                if not actions:
                    return 0

                logger.debug(f"[{thread_name}] Found {len(actions)} pending GoodwillActions.")
                
                for action in actions:
                    try:
                        process_goodwill_action_with_ailee_and_love(action.id)
                        processed_count += 1
                        logger.debug(f"[{thread_name}] Successfully processed GoodwillAction ID: {action.id}")
                    except Exception as e:
                        logger.error(f"[{thread_name}] Failed to process GoodwillAction ID {action.id}: {e}", exc_info=True)
                        action.status = 'failed'
                        session.add(action)

                return processed_count

        try:
            actual_processed_count = retry_db_operation(
                db_op_fetch_and_process,
                retries=self.app.config.get("AILEE_RETRIES", 3),
                delay=self.app.config.get("AILEE_RETRY_DELAY", 2)
            )
            if actual_processed_count > 0:
                logger.info(f"[{thread_name}] Successfully processed {actual_processed_count} action(s) in batch.")
            return actual_processed_count
        except Exception as e:
            logger.error(f"[{thread_name}] Failed to process batch after all retries: {e}", exc_info=True)
            return 0

# Singleton instance of EndocrineSystem
endocrine_system = EndocrineSystem()
