import os
import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from flask import Flask

from peoples_coin.models.db_utils import get_session_scope, retry_db_operation
from peoples_coin.models.models import GoodwillAction
from peoples_coin.config import Config

# AI goodwill action processor function
from peoples_coin.ai_processor.processor import process_goodwill_action

# Optional Celery task import
try:
    from peoples_coin.ailee.ailee_and_love import process_goodwill_action_task
except ImportError:
    process_goodwill_action_task = None

logger = logging.getLogger(__name__)


class EndocrineSystem:
    """
    Endocrine System manages asynchronous processing of VERIFIED GoodwillActions.
    Uses a thread pool to process actions in batches, optionally dispatching Celery tasks.
    """

    def __init__(self):
        self.app: Optional[Flask] = None
        self.executor: Optional[ThreadPoolExecutor] = None
        self._stop_event = threading.Event()
        self._initialized = False
        logger.info("🧠 EndocrineSystem instance created.")

    def init_app(self, app: Flask, loop_delay: int = 5, max_workers: int = 2):
        """
        Initialize with Flask app, worker count, and loop delay.
        Validates Celery task availability if enabled.
        """
        if self._initialized:
            logger.warning("⚠️ EndocrineSystem already initialized.")
            return

        self.app = app
        self.loop_delay = loop_delay
        self.max_workers = max_workers

        if app.config.get("USE_CELERY_FOR_GOODWILL", False) and not process_goodwill_action_task:
            raise RuntimeError(
                "USE_CELERY_FOR_GOODWILL is True but Celery task is not available."
            )

        self.executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix='EndocrineWorker'
        )
        self._initialized = True
        logger.info(f"🧠 EndocrineSystem initialized: {self.max_workers} workers, loop delay {self.loop_delay}s.")

    def start(self):
        """
        Starts worker threads for batch processing GoodwillActions.
        """
        if not self._initialized or not self.executor:
            logger.error("🚫 Cannot start: EndocrineSystem not initialized.")
            return

        if self.is_running():
            logger.warning("⚠️ EndocrineSystem already running.")
            return

        logger.info("▶️ Starting Endocrine worker pool...")
        self._stop_event.clear()
        for _ in range(self.max_workers):
            self.executor.submit(self._worker_loop)
        logger.info("🧵 All worker tasks submitted to the pool.")

    def stop(self):
        """
        Gracefully stops all worker threads.
        """
        if not self.is_running():
            logger.warning("⚠️ EndocrineSystem is not running.")
            return

        logger.info("⏹️ Stopping all worker threads...")
        self._stop_event.set()
        self.executor.shutdown(wait=True, cancel_futures=False)
        logger.info("🧵 All worker threads stopped gracefully.")

    def is_running(self) -> bool:
        """
        Returns True if the thread pool is active.
        """
        return self.executor is not None and not self.executor._shutdown

    def _worker_loop(self):
        """
        Each worker thread runs this loop to fetch and process goodwill actions.
        Waits loop_delay seconds if no work was found.
        """
        thread_name = threading.current_thread().name
        logger.info(f"[{thread_name}] 🧵 Worker thread started.")

        with self.app.app_context():
            while not self._stop_event.is_set():
                try:
                    processed_count = self._process_goodwill_actions_batch()
                    if processed_count == 0:
                        self._stop_event.wait(self.loop_delay)
                except Exception as e:
                    logger.error(f"[{thread_name}] 💥 Unrecoverable error in worker loop: {e}", exc_info=True)
                    self._stop_event.wait(self.loop_delay * 5)

        logger.info(f"[{thread_name}] 💤 Worker thread exiting.")

    def _process_goodwill_actions_batch(self) -> int:
        """
        Query for VERIFIED GoodwillActions and process them.
        Dispatches to Celery if enabled, otherwise runs synchronously.
        Returns count of processed actions.
        """
        thread_name = threading.current_thread().name
        use_celery = self.app.config.get("USE_CELERY_FOR_GOODWILL", False)

        def db_op():
            processed_count = 0
            with get_session_scope(self.app.extensions['sqlalchemy'].db) as session:
                actions = (
                    session.query(GoodwillAction)
                    .filter_by(status='VERIFIED')
                    .limit(self.app.config.get("AILEE_BATCH_SIZE", 5))
                    .all()
                )

                if not actions:
                    logger.debug(f"[{thread_name}] No VERIFIED GoodwillActions found.")
                    return 0

                logger.debug(f"[{thread_name}] Found {len(actions)} VERIFIED GoodwillActions.")

                for action in actions:
                    try:
                        if use_celery:
                            if process_goodwill_action_task:
                                process_goodwill_action_task.delay(str(action.id))
                                logger.debug(f"[{thread_name}] 📨 Dispatched to Celery: GoodwillAction ID: {action.id}")
                            else:
                                logger.error(f"[{thread_name}] Celery task not available despite USE_CELERY_FOR_GOODWILL=True.")
                                action.status = 'FAILED_DISPATCH'
                                session.add(action)
                        else:
                            success = process_goodwill_action(action.id, self.app.extensions['sqlalchemy'].db, self.app.config)
                            if success:
                                logger.info(f"[{thread_name}] ✅ Processed GoodwillAction {action.id}")
                            else:
                                logger.error(f"[{thread_name}] ❌ Failed to process GoodwillAction {action.id}")

                        processed_count += 1

                    except Exception as e:
                        logger.error(f"[{thread_name}] ❌ Failed to process ID {action.id} in batch: {e}", exc_info=True)
                        action.status = 'FAILED_ENDOCRINE_BATCH'
                        session.add(action)

            return processed_count

        try:
            actual_processed = retry_db_operation(
                db_op,
                retries=self.app.config.get("AILEE_RETRIES", 3),
                delay=self.app.config.get("AILEE_RETRY_DELAY", 2)
            )

            if actual_processed > 0:
                logger.info(f"[{thread_name}] 🎯 Processed {actual_processed} action(s) in this batch.")
            else:
                logger.debug(f"[{thread_name}] ⏳ No actions processed this cycle.")
            return actual_processed

        except Exception as e:
            logger.error(f"[{thread_name}] 🛑 Failed to process batch after retries: {e}", exc_info=True)
            return 0


# Singleton instance for import and use
endocrine_system = EndocrineSystem()

