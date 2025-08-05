# src/peoples_coin/systems/endocrine_system.py

import threading
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Callable

from flask import Flask

from peoples_coin.models.db_utils import get_session_scope, retry_db_operation
from peoples_coin.models.goodwill_action import GoodwillAction
from peoples_coin.extensions import db, celery

logger = logging.getLogger(__name__)

class EndocrineSystem:
    """
    Manages asynchronous processing of VERIFIED GoodwillActions using a thread pool.
    This system acts as a job queue processor, ensuring each action is processed once.
    """

    def __init__(self):
        self.app: Optional[Flask] = None
        self.executor: Optional[ThreadPoolExecutor] = None
        self.ai_processor_func: Optional[Callable] = None
        self._stop_event = threading.Event()
        self._initialized = False
        logger.info("🧠 EndocrineSystem instance created.")

    def init_app(self, app: Flask, ai_processor_func: Callable):
        """Initializes the system with the Flask app and dependencies."""
        if self._initialized:
            return

        self.app = app
        self.ai_processor_func = ai_processor_func
        self.max_workers = app.config.get("AILEE_MAX_WORKERS", 2)
        self.loop_delay = app.config.get("AILEE_RETRY_DELAY", 5)

        if app.config.get("USE_CELERY_FOR_GOODWILL") and not celery:
            raise RuntimeError("Configuration specifies Celery, but Celery task is not available.")

        self.executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix='EndocrineWorker')
        self._initialized = True
        logger.info(f"🧠 EndocrineSystem initialized: {self.max_workers} workers, loop delay {self.loop_delay}s.")

    def start(self):
        """Starts the worker threads to process GoodwillActions."""
        if not self._initialized or not self.executor:
            raise RuntimeError("Cannot start: EndocrineSystem not initialized.")
        if self.is_running():
            logger.warning("⚠️ EndocrineSystem already running.")
            return

        logger.info("▶️ Starting Endocrine worker pool...")
        self._stop_event.clear()
        for _ in range(self.max_workers):
            self.executor.submit(self._worker_loop)

    def stop(self):
        """Gracefully stops all worker threads."""
        if not self.is_running():
            return
        logger.info("⏹️ Stopping Endocrine worker threads...")
        self._stop_event.set()
        self.executor.shutdown(wait=True)
        logger.info("🧵 All Endocrine worker threads stopped.")

    def is_running(self) -> bool:
        """Returns True if the thread pool is active."""
        return self.executor is not None and not self.executor._shutdown

    def _worker_loop(self):
        """The main loop for each worker thread."""
        thread_name = threading.current_thread().name
        logger.info(f"[{thread_name}] 🧵 Worker thread started.")
        with self.app.app_context():
            while not self._stop_event.is_set():
                try:
                    processed_count = self._process_goodwill_actions_batch()
                    if processed_count == 0:
                        self._stop_event.wait(self.loop_delay) # Wait if no work was found
                except Exception as e:
                    logger.error(f"[{thread_name}] 💥 Unrecoverable error in worker loop: {e}", exc_info=True)
                    self._stop_event.wait(self.loop_delay * 5) # Longer backoff on error
        logger.info(f"[{thread_name}] 💤 Worker thread exiting.")

    def _process_goodwill_actions_batch(self) -> int:
        """
        Queries for a unique batch of VERIFIED GoodwillActions using row-level locking
        and dispatches them for processing. Returns the number of actions processed.
        """
        use_celery = self.app.config.get("USE_CELERY_FOR_GOODWILL", False)
        batch_size = self.app.config.get("AILEE_BATCH_SIZE", 5)

        def db_op():
            with get_session_scope() as session:
                # **CRITICAL FIX**: Use `with_for_update(skip_locked=True)` to prevent race conditions.
                # This ensures each worker gets a unique set of rows to process, effectively
                # turning the database table into a reliable job queue.
                query = session.query(GoodwillAction).filter(GoodwillAction.status == 'VERIFIED')
                if self.app.config.get("DB_SUPPORTS_SKIP_LOCKED", True):
                    query = query.with_for_update(skip_locked=True)
                
                actions_to_process = query.limit(batch_size).all()

                if not actions_to_process:
                    return 0

                for action in actions_to_process:
                    try:
                        # Mark the action as PROCESSING immediately to prevent it from being picked up again
                        # even if SKIP LOCKED is not available.
                        action.status = 'PROCESSING'
                        session.commit() # Commit this small change immediately

                        if use_celery:
                            # from peoples_coin.tasks import process_goodwill_action_task
                            # process_goodwill_action_task.delay(str(action.id))
                            logger.info(f"📨 Dispatched to Celery: GoodwillAction ID: {action.id}")
                        else:
                            self.ai_processor_func(action.id)
                            logger.info(f"✅ Processed GoodwillAction {action.id} synchronously.")
                    
                    except Exception as e:
                        logger.error(f"❌ Failed to process ID {action.id} in batch: {e}", exc_info=True)
                        session.rollback()
                        action.status = 'FAILED_ENDOCRINE_BATCH'
                        session.add(action)
                        session.commit()

                return len(actions_to_process)
        
        try:
            return retry_db_operation(db_op)
        except Exception as e:
            logger.error(f"🛑 Failed to process batch after retries: {e}", exc_info=True)
            return 0

# Singleton instance for import and use across the application
endocrine_system = EndocrineSystem()
