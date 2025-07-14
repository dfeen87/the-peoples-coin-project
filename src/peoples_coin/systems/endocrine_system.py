import threading
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from flask import Flask

from ..extensions import db
from ..db.db_utils import get_session_scope, retry_db_operation
from ..db.models import GoodwillAction
from ..config import Config

# If Celery is enabled
try:
    from peoples_coin.ailee.ailee_and_love import process_goodwill_action_task
except ImportError:
    process_goodwill_action_task = None

logger = logging.getLogger(__name__)


"""
🩺 EndocrineSystem: Background worker to process GoodwillActions.

📌 By default, this runs autonomously in worker threads inside your Flask app.
📌 If you set `USE_CELERY_FOR_GOODWILL = True` in your Config,
    the workers will delegate to Celery tasks instead (requires a running Celery worker & broker).

Current default: USE_CELERY_FOR_GOODWILL = False
"""


class EndocrineSystem:
    """
    The Endocrine System. Multi-threaded background worker controller.
    """

    def __init__(self):
        self.app: Optional[Flask] = None
        self.executor: Optional[ThreadPoolExecutor] = None
        self._stop_event = threading.Event()
        self._initialized = False
        logger.info("🧠 EndocrineSystem instance created.")

    def init_app(self, app: Flask, loop_delay: int = 5, max_workers: int = 2):
        if self._initialized:
            logger.warning("⚠️ EndocrineSystem already initialized.")
            return

        self.app = app
        self.loop_delay = loop_delay
        self.max_workers = max_workers

        if app.config.get("USE_CELERY_FOR_GOODWILL", False) and not process_goodwill_action_task:
            raise RuntimeError(
                "USE_CELERY_FOR_GOODWILL is True but Celery task is not available. "
                "Check your Celery setup or set USE_CELERY_FOR_GOODWILL = False."
            )

        self.executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix='EndocrineWorker'
        )
        self._initialized = True
        logger.info(f"🧠 EndocrineSystem initialized: {self.max_workers} workers, loop delay {self.loop_delay}s.")

    def start(self):
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
        if not self.is_running():
            logger.warning("⚠️ EndocrineSystem is not running.")
            return

        logger.info("⏹️ Stopping all worker threads...")
        self._stop_event.set()
        self.executor.shutdown(wait=True, cancel_futures=False)
        logger.info("🧵 All worker threads stopped gracefully.")

    def is_running(self) -> bool:
        return self.executor is not None and not self.executor._shutdown

    def _worker_loop(self):
        thread_name = threading.current_thread().name
        logger.info(f"[{thread_name}] 🧵 Worker thread started.")

        with self.app.app_context():
            while not self._stop_event.is_set():
                try:
                    processed_count = self._process_goodwill_actions_batch()
                    if processed_count == 0:
                        self._stop_event.wait(self.loop_delay)
                except Exception as e:
                    logger.error(f"[{thread_name}] 💥 Unrecoverable error: {e}", exc_info=True)
                    self._stop_event.wait(self.loop_delay * 5)

        logger.info(f"[{thread_name}] 💤 Worker thread exiting.")

    def _process_goodwill_actions_batch(self) -> int:
        thread_name = threading.current_thread().name
        use_celery = self.app.config.get("USE_CELERY_FOR_GOODWILL", False)

        def db_op():
            processed_count = 0
            with get_session_scope(db) as session:
                actions = (
                    session.query(GoodwillAction)
                    .filter_by(status='pending')
                    .limit(self.app.config.get("AILEE_BATCH_SIZE", 5))
                    .all()
                )

                if not actions:
                    logger.debug(f"[{thread_name}] No pending GoodwillActions found.")
                    return 0

                logger.debug(f"[{thread_name}] Found {len(actions)} pending GoodwillActions.")

                for action in actions:
                    try:
                        if use_celery:
                            process_goodwill_action_task.delay(action.id)
                            logger.debug(f"[{thread_name}] 📨 Dispatched to Celery: GoodwillAction ID: {action.id}")
                            action.status = 'queued'
                        else:
                            from ..ai_processor.processor import process_goodwill_action_with_ailee_and_love
                            process_goodwill_action_with_ailee_and_love(action.id)
                            logger.debug(f"[{thread_name}] ✅ Processed GoodwillAction ID: {action.id}")
                            action.status = 'processed'

                        session.add(action)
                        processed_count += 1

                    except Exception as e:
                        logger.error(f"[{thread_name}] ❌ Failed to process ID {action.id}: {e}", exc_info=True)
                        action.status = 'failed'
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


# Singleton instance
endocrine_system = EndocrineSystem()

