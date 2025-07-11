# peoples_coin/peoples_coin/systems/endocrine_system.py

import threading
import logging
import time

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from ..db import db
from ..db.models import GoodwillAction

logger = logging.getLogger(__name__)

class AILEEController:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, app=None, db=None, loop_delay=5, max_workers=2):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(app=app, db=db, loop_delay=loop_delay, max_workers=max_workers)
        return cls._instance

    def __init__(self, app=None, db=None, loop_delay=5, max_workers=2):
        if not hasattr(self, '_initialized'):
            self.app = app
            self.db = db
            self.loop_delay = loop_delay
            self.max_workers = max_workers
            self._stop_event = threading.Event()
            self._worker_threads = []
            self._initialized = True
            logger.info("AILEEController initialized.")

    def start(self):
        logger.info("[AILEE] Starting %d worker threads...", self.max_workers)
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
        logger.info("[AILEE] Stopping all worker threads...")
        self._stop_event.set()
        for thread in self._worker_threads:
            thread.join(timeout=self.loop_delay + 5)
        logger.info("[AILEE] All worker threads stopped.")

    def _worker_loop(self):
        thread_name = threading.current_thread().name
        logger.info(f"[{thread_name}] Worker thread started.")

        with self.app.app_context():
            while not self._stop_event.is_set():
                try:
                    processed = self._process_goodwill_actions_batch()
                    if processed == 0:
                        # Sleep efficiently until next poll or stop event
                        self._stop_event.wait(self.loop_delay)
                except (OperationalError, StaleDataError) as db_err:
                    logger.warning(f"[{thread_name}] Database error: {db_err}. Retrying after delay...")
                    self.db.session.rollback()
                    self._stop_event.wait(self.loop_delay)
                except Exception as e:
                    logger.error(f"[{thread_name}] Unexpected error: {e}", exc_info=True)
                    self._stop_event.wait(self.loop_delay)

        logger.info(f"[{thread_name}] Worker thread exiting.")

    def _process_goodwill_actions_batch(self) -> int:
        thread_name = threading.current_thread().name
        session = self.db.session

        try:
            actions = session.query(GoodwillAction).filter_by(status='pending').limit(5).all()

            if not actions:
                logger.debug(f"[{thread_name}] No pending GoodwillAction found.")
                return 0

            logger.info(f"[{thread_name}] Processing {len(actions)} GoodwillAction(s).")

            for action in actions:
                # TODO: Replace this with actual processing logic
                action.status = 'completed'
                session.add(action)

            session.commit()
            logger.info(f"[{thread_name}] Committed {len(actions)} GoodwillAction(s) as completed.")
            return len(actions)

        except Exception as e:
            logger.error(f"[{thread_name}] Failed to process GoodwillActions: {e}", exc_info=True)
            session.rollback()
            return 0

