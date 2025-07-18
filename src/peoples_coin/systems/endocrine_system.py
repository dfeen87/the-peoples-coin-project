import os
import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Callable, Dict, Any
import uuid # For UUID if needed

from flask import request, jsonify, Flask, g

try:
    from redis import Redis, exceptions as RedisExceptions
except ImportError:
    Redis = None
    RedisExceptions = None

# Import the CirculatorySystem instance
from peoples_coin.systems.circulatory_system import circulatory_system
from peoples_coin.db.db_utils import get_session_scope, retry_db_operation
from peoples_coin.db.models import GoodwillAction # Ensure GoodwillAction is imported
from peoples_coin.config import Config # Ensure Config is imported

# If Celery is enabled
try:
    from peoples_coin.ailee.ailee_and_love import process_goodwill_action_task # This task will now call circulatory_system
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
    Responsible for picking up VERIFIED GoodwillActions and passing them
    to the CirculatorySystem for on-chain minting.
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

        # Ensure Celery task is available if configured to use Celery
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

        with self.app.app_context(): # Ensure app context for DB operations
            while not self._stop_event.is_set():
                try:
                    processed_count = self._process_goodwill_actions_batch()
                    if processed_count == 0:
                        self._stop_event.wait(self.loop_delay) # Wait if no actions processed
                except Exception as e:
                    logger.error(f"[{thread_name}] 💥 Unrecoverable error in worker loop: {e}", exc_info=True)
                    self._stop_event.wait(self.loop_delay * 5) # Longer wait on error

        logger.info(f"[{thread_name}] 💤 Worker thread exiting.")

    def _process_goodwill_actions_batch(self) -> int:
        thread_name = threading.current_thread().name
        use_celery = self.app.config.get("USE_CELERY_FOR_GOODWILL", False)

        def db_op():
            processed_count = 0
            with get_session_scope(db) as session:
                # Query for GoodwillActions that are VERIFIED and ready for minting
                actions = (
                    session.query(GoodwillAction)
                    .filter_by(status='VERIFIED') # Only process VERIFIED actions
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
                            # If using Celery, dispatch the action ID to a Celery task
                            # This task will then call circulatory_system.process_goodwill_for_minting
                            if process_goodwill_action_task: # Ensure task is imported
                                process_goodwill_action_task.delay(str(action.id)) # Pass UUID as string
                                logger.debug(f"[{thread_name}] 📨 Dispatched to Celery: GoodwillAction ID: {action.id}")
                                # Status will be updated by the Celery task after processing by CirculatorySystem
                            else:
                                logger.error(f"[{thread_name}] Celery task not available despite USE_CELERY_FOR_GOODWILL=True.")
                                action.status = 'FAILED_DISPATCH' # New status for dispatch failure
                                session.add(action)
                        else:
                            # If not using Celery, process directly within this thread
                            # Call the CirculatorySystem directly for minting
                            success, msg = circulatory_system.process_goodwill_for_minting(action.id)
                            if success:
                                logger.debug(f"[{thread_name}] ✅ Processed GoodwillAction ID: {action.id} (in-app). Message: {msg}")
                                # Status is updated by circulatory_system.process_goodwill_for_minting
                            else:
                                logger.error(f"[{thread_name}] ❌ Failed to process GoodwillAction ID {action.id} (in-app). Message: {msg}")
                                # Status is updated by circulatory_system.process_goodwill_for_minting
                        
                        processed_count += 1

                    except Exception as e:
                        logger.error(f"[{thread_name}] ❌ Failed to process ID {action.id} in batch: {e}", exc_info=True)
                        # If an error occurs here, it might be before circulatory_system updates status
                        # So, set to a generic failed state or ensure circulatory_system handles all failures
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


# Singleton instance
endocrine_system = EndocrineSystem()
