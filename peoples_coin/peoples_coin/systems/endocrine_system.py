import threading
import time
import logging
import random
import json
# Removed 'queue' import as we're no longer using in-memory queue
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError

from dotenv import load_dotenv
load_dotenv()

from peoples_coin.peoples_coin.db.db import db
from peoples_coin.peoples_coin.db.models import DataEntry, GoodwillAction # Import models

try:
    from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


class AILEEController:
    _instance = None
    _lock = threading.Lock()

    MAX_STOP_JOIN_TIMEOUT = 10
    MAX_RETRIES = 3
    BASE_RETRY_DELAY = 1
    TASK_POLLING_INTERVAL = 2 # New: How often workers check the DB for tasks (seconds)

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(AILEEController, cls).__new__(cls)
                    cls._instance._attributes_initialized = False 
        return cls._instance

    def __init__(self, app=None, db=None, loop_delay=5, max_workers=2, log_level=logging.INFO):
        if not self._attributes_initialized:
            self.app = app
            self.db = db
            self.loop_delay = loop_delay
            self.log_level = log_level
            self.max_workers = max_workers

            self._internal_lock = threading.Lock()
            self._running = False
            self._stop_requested = threading.Event()
            
            self.main_loop_thread = None
            self.worker_threads = []
            
            # Removed: self.task_queue = queue.Queue() # No longer using in-memory queue

            self._last_run_time = None
            self._start_time = None
            self._cycle_count = 0

            self.on_start = []
            self.on_stop = []
            self.on_cycle_start = []
            self.on_cycle_end = []
            self.on_error = []
            self.on_alert = []
            self.on_audit = []
            self.processing_plugins = []

            self._config_lock = threading.Lock()

            if PROMETHEUS_AVAILABLE:
                self._metrics_setup()

            if self.db and (not hasattr(self, '_audit_listener_attached') or not self._audit_listener_attached):
                self._setup_audit_listener()
            
            self.logger = logging.getLogger("AILEEController")
            self.logger.setLevel(self.log_level)

            self.logger.info("AILEEController initialized (or retrieved existing instance)")
            self._attributes_initialized = True

    @classmethod
    def get_instance(cls, app=None, db=None, loop_delay=5, max_workers=2, log_level=logging.INFO):
        instance = cls.__new__(cls)
        if not instance._attributes_initialized:
            if app is None or db is None:
                raise ValueError("AILEEController must be initialized with 'app' and 'db' on its first call to get_instance().")
            instance.__init__(app=app, db=db, loop_delay=loop_delay, max_workers=max_workers, log_level=log_level)
        return instance

    def _metrics_setup(self):
        self.metrics_cycles_total = Counter("ailee_cycles_total", "Total AI processing cycles executed")
        self.metrics_entries_processed = Counter("ailee_entries_processed_total", "Total DB entries processed")
        self.metrics_cycle_duration = Histogram("ailee_cycle_duration_seconds", "Duration of AI processing cycles")
        self.metrics_errors_total = Counter("ailee_errors_total", "Total errors encountered in AILEEController")
        self.metrics_errors_by_type = Counter(
            "ailee_errors_by_type_total", "Errors by type",
            ['error_type']
        )
        self.metrics_hooks_executed = Counter(
            "ailee_hooks_executed_total", "Hooks executed by type",
            ['hook_type']
        )
        self.metrics_hooks_failed = Counter(
            "ailee_hooks_failed_total", "Hook failures by type",
            ['hook_type']
        )
        self.metrics_active_workers = Gauge(
            "ailee_active_workers", "Number of active worker threads"
        )
        self.metrics_running = Gauge("ailee_running", "Is the AILEEController running (1 for yes, 0 for no)")

    def _log(self, level, msg, exc_info=False):
        self.logger.log(level, f"[AILEE] {datetime.now(timezone.utc).isoformat()} - {msg}", exc_info=exc_info)

    def _alert(self, msg):
        self._log(logging.CRITICAL, f"ALERT: {msg}")
        for hook in self.on_alert:
            try:
                hook(msg)
                if PROMETHEUS_AVAILABLE:
                    self.metrics_hooks_executed.labels('on_alert').inc()
            except Exception:
                self._log(logging.ERROR, "Error in alert hook", exc_info=True)
                if PROMETHEUS_AVAILABLE:
                    self.metrics_hooks_failed.labels('on_alert').inc()

    def _audit(self, entry, action):
        audit_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "entry_id": getattr(entry, "id", None),
            "action": action,
            "entry_snapshot": self._serialize_entry(entry)
        }
        self._log(logging.INFO, f"Audit record: {json.dumps(audit_record)}")
        for hook in self.on_audit:
            try:
                hook(audit_record)
                if PROMETHEUS_AVAILABLE:
                    self.metrics_hooks_executed.labels('on_audit').inc()
            except Exception:
                self._log(logging.ERROR, "Error in audit hook", exc_info=True)
                if PROMETHEUS_AVAILABLE:
                    self.metrics_hooks_failed.labels('on_audit').inc()

    def _serialize_entry(self, entry):
        try:
            if hasattr(entry, 'to_dict') and callable(entry.to_dict):
                return entry.to_dict()
            else:
                return {c.name: getattr(entry, c.name) for c in entry.__table__.columns}
        except Exception:
            return str(entry)

    def _retry_db_operation(self, func, *args, **kwargs):
        for attempt in range(1, self.MAX_RETRIES + 1):
            if self._stop_requested.is_set():
                self._log(logging.INFO, "Stop requested, aborting DB operation retry")
                return None
            try:
                return func(*args, **kwargs)
            except SQLAlchemyError as e:
                if PROMETHEUS_AVAILABLE:
                    self.metrics_errors_total.inc()
                    self.metrics_errors_by_type.labels('db').inc()
                self._log(logging.WARNING, f"DB error attempt {attempt}/{self.MAX_RETRIES}: {e}", exc_info=True)
                if attempt == self.MAX_RETRIES:
                    self._alert(f"Persistent DB failure after {self.MAX_RETRIES} attempts: {e}")
                    raise
                sleep_time = self.BASE_RETRY_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                time.sleep(sleep_time)

    def register_processing_plugin(self, func):
        if not callable(func):
            raise ValueError("Plugin must be callable")
        self.processing_plugins.append(func)
        self._log(logging.INFO, f"Registered processing plugin: {func}")

    def _process_data_entry(self, entry):
        try:
            for plugin in self.processing_plugins:
                plugin(self, entry)
            entry.processed = True
            self._audit(entry, "processed")
        except Exception as e:
            if PROMETHEUS_AVAILABLE:
                self.metrics_errors_total.inc()
                self.metrics_errors_by_type.labels('processing').inc()
            self._log(logging.ERROR, f"Error processing DataEntry ID {getattr(entry, 'id', 'unknown')}: {e}", exc_info=True)
            raise

    def _process_data_entries_batch(self):
        with self.app.app_context():
            try:
                unprocessed = self.db.session.query(DataEntry).filter(DataEntry.processed == False).limit(10).all()
                processed_count = 0
                for entry in unprocessed:
                    if self._stop_requested.is_set():
                        self._log(logging.INFO, "Stop requested, interrupting DataEntry processing.")
                        break
                    try:
                        self._process_data_entry(entry)
                        processed_count += 1
                    except Exception:
                        self._log(logging.ERROR, f"Error during DataEntry processing for ID {entry.id}", exc_info=True)

                if processed_count > 0:
                    try:
                        self.db.session.commit()
                        self._log(logging.INFO, f"Committed {processed_count} DataEntry updates.")
                    except Exception as e:
                        self.db.session.rollback()
                        self._log(logging.ERROR, f"DataEntry batch commit failed: {e}", exc_info=True)
                
                if PROMETHEUS_AVAILABLE:
                    self.metrics_entries_processed.inc(processed_count)

                return processed_count
            except Exception as e:
                self.logger.error(f"Failed to query or process DataEntry batch: {e}", exc_info=True)
                return 0
            finally:
                self.db.session.remove() 

    def _main_ailee_loop(self):
        self.logger.info(f"[AILEE] AILEE main loop started, will run every {self.loop_delay} seconds.")
        if PROMETHEUS_AVAILABLE:
            self.metrics_running.set(1)

        while self._running and not self._stop_requested.is_set():
            cycle_start_time = datetime.now(timezone.utc)
            self._cycle_count += 1
            self._log(logging.INFO, f"Starting cycle #{self._cycle_count}")

            for hook in self.on_cycle_start:
                try:
                    hook(self._cycle_count)
                    if PROMETHEUS_AVAILABLE:
                        self.metrics_hooks_executed.labels('on_cycle_start').inc()
                except Exception as e:
                    self._log(logging.ERROR, f"Error in on_cycle_start hook: {e}", exc_info=True)
                    if PROMETHEUS_AVAILABLE:
                        self.metrics_hooks_failed.labels('on_cycle_start').inc()

            try:
                processed_entries_count = self._process_data_entries_batch()
                self._log(logging.INFO, f"Processed {processed_entries_count} DataEntry items this cycle")

                if PROMETHEUS_AVAILABLE:
                    self.metrics_cycles_total.inc()

            except Exception as e:
                if PROMETHEUS_AVAILABLE:
                    self.metrics_errors_total.inc()
                    self.metrics_errors_by_type.labels('cycle').inc()
                self._log(logging.ERROR, f"Exception during AILEE main cycle {self._cycle_count}: {e}", exc_info=True)
                for hook in self.on_error:
                    try:
                        hook(e)
                        if PROMETHEUS_AVAILABLE:
                            self.metrics_hooks_executed.labels('on_error').inc()
                    except Exception:
                        self._log(logging.ERROR, "Error in on_error hook", exc_info=True)
                        if PROMETHEUS_AVAILABLE:
                            self.metrics_hooks_failed.labels('on_error').inc()

            for hook in self.on_cycle_end:
                try:
                    hook(self._cycle_count)
                    if PROMETHEUS_AVAILABLE:
                        self.metrics_hooks_executed.labels('on_cycle_end').inc()
                except Exception as e:
                    self._log(logging.ERROR, f"Error in on_cycle_end hook: {e}", exc_info=True)
                    if PROMETHEUS_AVAILABLE:
                        self.metrics_hooks_failed.labels('on_cycle_end').inc()

            elapsed_time = (datetime.now(timezone.utc) - cycle_start_time).total_seconds()
            sleep_duration = max(0, self.loop_delay - elapsed_time)
            
            self._stop_requested.wait(timeout=sleep_duration)
            
            self._log(logging.DEBUG, f"Completed cycle #{self._cycle_count}")

        self._log(logging.INFO, "AILEE main loop exiting.")
        if PROMETHEUS_AVAILABLE:
            self.metrics_running.set(0)


    def run_task_worker(self, worker_id):
        """Worker thread function to poll the database for pending GoodwillActions."""
        self.logger.info(f"[AILEE] AILEEWorker-{worker_id} started processing loop for tasks (DB polling).")
        if PROMETHEUS_AVAILABLE:
            self.metrics_active_workers.inc()

        try:
            while self._running and not self._stop_requested.is_set():
                self._log(logging.DEBUG, f"[AILEE] AILEEWorker-{worker_id}: Polling database for pending GoodwillActions...")
                goodwill_action_obj = None # Initialize to None

                # Fetch a pending GoodwillAction from the database within its own app context
                with self.app.app_context():
                    try:
                        # Attempt to find and lock a pending GoodwillAction
                        # This uses a simple optimistic locking strategy by checking status again after query
                        goodwill_action_obj = self.db.session.query(GoodwillAction).filter_by(status='pending').first()

                        if goodwill_action_obj:
                            self._log(logging.DEBUG, f"[AILEE] AILEEWorker-{worker_id}: Found pending GoodwillAction ID {goodwill_action_obj.id}. Attempting to set status to 'processing'.")
                            
                            # Re-query and lock to ensure atomicity in a multi-worker scenario
                            # This is a basic form of locking; for high concurrency, proper DB locks might be needed.
                            locked_action = self.db.session.query(GoodwillAction).filter_by(id=goodwill_action_obj.id, status='pending').with_for_update().first()
                            
                            if locked_action:
                                locked_action.status = 'processing'
                                self.db.session.commit()
                                self.logger.info(f"[AILEE] AILEEWorker-{worker_id}: Set GoodwillAction ID {locked_action.id} to 'processing'.")
                                goodwill_action_obj = locked_action # Use the locked object for further processing
                            else:
                                self._log(logging.DEBUG, f"[AILEE] AILEEWorker-{worker_id}: GoodwillAction ID {goodwill_action_obj.id} was already picked up by another worker. Skipping.")
                                goodwill_action_obj = None # Reset to None if it was already processed
                                # Continue to next loop iteration to check for new tasks
                                self.db.session.remove() # Clean up session even if no task was processed
                                self._stop_requested.wait(timeout=self.TASK_POLLING_INTERVAL) # Wait before next poll
                                continue # Skip to next loop iteration

                        else:
                            self._log(logging.DEBUG, f"[AILEE] AILEEWorker-{worker_id}: No pending GoodwillActions found. Waiting {self.TASK_POLLING_INTERVAL}s.")
                            self.db.session.remove() # Clean up session if no task was processed
                            self._stop_requested.wait(timeout=self.TASK_POLLING_INTERVAL) # Wait before next poll
                            continue # Skip to next loop iteration if no task found

                    except SQLAlchemyError as db_err:
                        self.db.session.rollback()
                        self.logger.error(f"[AILEE] AILEEWorker-{worker_id}: Database error during task retrieval/locking: {db_err}", exc_info=True)
                        self.db.session.remove() # Ensure session is cleaned up after rollback
                        self._stop_requested.wait(timeout=self.TASK_POLLING_INTERVAL) # Wait before next poll
                        continue # Skip to next loop iteration

                # Process the GoodwillAction if successfully locked
                if goodwill_action_obj:
                    self.logger.info(f"[AILEE] AILEEWorker-{worker_id}: Processing GoodwillAction ID: {goodwill_action_obj.id}")
                    
                    with self.app.app_context(): # Re-enter context for processing and final update
                        try:
                            # --- Perform AILEE calculations ---
                            self._log(logging.DEBUG, f"[AILEE] AILEEWorker-{worker_id}: Calling calculate_goodwill_resonance for ID {goodwill_action_obj.id}.")
                            raw_score, resonance_score = self.calculate_goodwill_resonance(goodwill_action_obj)
                            self._log(logging.DEBUG, f"[AILEE] AILEEWorker-{worker_id}: Calculation complete for ID {goodwill_action_obj.id}. Raw={raw_score}, Resonance={resonance_score}.")

                            # Update the GoodwillAction in the database with scores and status
                            # Re-fetch to ensure we have the latest state before updating
                            action_to_update = self.db.session.get(GoodwillAction, goodwill_action_obj.id)
                            if action_to_update:
                                action_to_update.raw_goodwill_score = raw_score
                                action_to_update.resonance_score = resonance_score
                                action_to_update.status = 'completed'
                                action_to_update.processed_at = datetime.now(timezone.utc)
                                self._log(logging.DEBUG, f"[AILEE] AILEEWorker-{worker_id}: Committing updated scores for ID {action_to_update.id}.")
                                self.db.session.commit()
                                self.logger.info(f"[AILEE] AILEEWorker-{worker_id}: Updated GoodwillAction ID {action_to_update.id} in DB with scores and status 'completed'.")
                            else:
                                self.logger.error(f"[AILEE] AILEEWorker-{worker_id}: Failed to re-fetch GoodwillAction ID {goodwill_action_obj.id} for final update.")

                        except Exception as e:
                            self.db.session.rollback()
                            self.logger.error(f"[AILEE] AILEEWorker-{worker_id}: Error during GoodwillAction processing or final update for ID {goodwill_action_obj.id}: {e}", exc_info=True)
                            # Attempt to update status to 'failed'
                            with self.app.app_context():
                                try:
                                    failed_action = self.db.session.get(GoodwillAction, goodwill_action_obj.id)
                                    if failed_action and failed_action.status != 'completed': # Don't overwrite if already completed
                                        failed_action.status = 'failed'
                                        self.db.session.commit()
                                        self.logger.info(f"[AILEE] AILEEWorker-{worker_id}: Set GoodwillAction ID {goodwill_action_obj.id} to 'failed' due to error.")
                                except Exception as rollback_e:
                                    self.db.session.rollback()
                                    self.logger.error(f"[AILEE] AILEEWorker-{worker_id}: Error updating status to 'failed' for ID {goodwill_action_obj.id}: {rollback_e}", exc_info=True)
                                finally:
                                    self.db.session.remove() # Clean up nested session
                        finally:
                            self.db.session.remove() # Ensure session is cleaned up after processing

                else:
                    # If goodwill_action_obj is None (e.g., if it was already picked up)
                    # We already handled the wait and continue in the initial fetch block
                    pass

                # Wait for a short period before polling again, even if a task was processed
                self._stop_requested.wait(timeout=self.TASK_POLLING_INTERVAL)
            
            self.logger.info(f"[AILEE] AILEE worker thread AILEEWorker-{worker_id} loop finished.")

        except Exception as e:
            self.logger.critical(f"[AILEE] AILEEWorker-{worker_id}: CRITICAL: Worker thread terminated unexpectedly due to: {e}", exc_info=True)
        finally:
            if PROMETHEUS_AVAILABLE:
                self.metrics_active_workers.dec()
            self.logger.info(f"[AILEE] AILEE worker thread AILEEWorker-{worker_id} exiting.")

    def _setup_audit_listener(self):
        if not hasattr(self, '_audit_listener_attached') or not self._audit_listener_attached:
            @event.listens_for(self.db.session, "after_flush")
            def after_flush(session, flush_context):
                for instance in session.new.union(session.dirty):
                    if isinstance(instance, DataEntry) and getattr(instance, "processed", False):
                        self._audit(instance, "db_flush")
            self._audit_listener_attached = True

    def start(self):
        with self._internal_lock:
            if self._running:
                self._log(logging.WARNING, "Start called but AILEE is already running")
                return
            self._running = True
            self._stop_requested.clear()
            self._start_time = datetime.now(timezone.utc)
            self._cycle_count = 0
            
            self.main_loop_thread = threading.Thread(target=self._main_ailee_loop, daemon=True, name="AILEEMainLoop")
            self.main_loop_thread.start()
            self._log(logging.INFO, f"AILEE main loop thread started.")

            self._log(logging.INFO, f"Attempting to launch {self.max_workers} AILEE worker threads now (DB polling mode).")

            self.worker_threads = []
            for i in range(self.max_workers):
                t = threading.Thread(target=self.run_task_worker, args=(i+1,), daemon=True, name=f"AILEEWorker-{i+1}")
                t.start()
                self.worker_threads.append(t)
            self._log(logging.INFO, f"AILEE task workers started with {self.max_workers} workers")

            active_threads = threading.enumerate()
            self._log(logging.INFO, f"DEBUG: Total active threads after AILEE worker launch: {len(active_threads)}")
            for t in active_threads:
                self._log(logging.INFO, f"DEBUG: Active thread: Name='{t.name}', Daemon={t.daemon}, Alive={t.is_alive()}")

            if PROMETHEUS_AVAILABLE:
                self.metrics_running.set(1)
            self._log(logging.INFO, f"AILEEController started with {self.max_workers} workers")

        for hook in self.on_start:
            try:
                hook()
                if PROMETHEUS_AVAILABLE:
                    self.metrics_hooks_executed.labels('on_start').inc()
            except Exception as e:
                self._log(logging.ERROR, f"Error in on_start hook: {e}", exc_info=True)
                if PROMETHEUS_AVAILABLE:
                    self.metrics_hooks_failed.labels('on_start').inc()

    def stop(self):
        with self._internal_lock:
            if not self._running:
                self._log(logging.WARNING, "Stop called but AILEE is not running")
                return
            self._running = False
            self._stop_requested.set()

        self._log(logging.INFO, "Stopping AILEEController... waiting for threads to finish")

        # Removed: Signaling workers via queue. No longer needed with DB polling.
        # for _ in self.worker_threads:
        #     self.task_queue.put(None) 

        for t in self.worker_threads:
            t.join(timeout=self.MAX_STOP_JOIN_TIMEOUT)
            if t.is_alive():
                self._log(logging.WARNING, f"Worker thread {t.name} did not stop within timeout")
            else:
                self._log(logging.INFO, f"Worker thread {t.name} stopped cleanly")
        self.worker_threads = []

        if self.main_loop_thread and self.main_loop_thread.is_alive():
            self.main_loop_thread.join(timeout=self.MAX_STOP_JOIN_TIMEOUT)
            if self.main_loop_thread.is_alive():
                self._log(logging.WARNING, "Main AILEE loop thread did not stop within timeout")
            else:
                self._log(logging.INFO, "Main AILEE loop thread stopped cleanly")
        self.main_loop_thread = None

        if PROMETHEUS_AVAILABLE:
            self.metrics_running.set(0)

        for hook in self.on_stop:
            try:
                hook()
                if PROMETHEUS_AVAILABLE:
                    self.metrics_hooks_executed.labels('on_stop').inc()
            except Exception as e:
                self._log(logging.ERROR, f"Error in on_stop hook: {e}", exc_info=True)
                if PROMETHEUS_AVAILABLE:
                    self.metrics_hooks_failed.labels('on_stop').inc()

        self._log(logging.INFO, "AILEEController stopped.")

    def restart(self):
        self.stop()
        self.start()

    def is_running(self):
        if not hasattr(self, '_internal_lock'):
            return False 
        with self._internal_lock:
            return self._running

    def status(self):
        if not hasattr(self, '_internal_lock'):
            return {"running": False, "message": "AILEEController not fully initialized."}

        with self._internal_lock:
            return {
                "running": self._running,
                "main_loop_thread_alive": self.main_loop_thread and self.main_loop_thread.is_alive(),
                "worker_threads_alive": [t.is_alive() for t in self.worker_threads],
                "cycle_count": self._cycle_count,
                "start_time": self._start_time.isoformat() if self._start_time else None,
                "last_run_time": self._last_run_time.isoformat() if self._last_run_time else None,
                "loop_delay_seconds": self.loop_delay,
                "max_workers": self.max_workers,
                # Removed: "task_queue_size": self.task_queue.qsize() # No longer relevant
            }

    def set_loop_delay(self, delay_seconds):
        if delay_seconds <= 0:
            raise ValueError("loop_delay must be positive")
        with self._config_lock:
            self.loop_delay = delay_seconds
            self._log(logging.INFO, f"AILEEController loop_delay updated to {delay_seconds} seconds")

    def set_max_workers(self, max_workers):
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        with self._config_lock:
            self.max_workers = max_workers
            self._log(logging.INFO, f"AILEEController max_workers updated to {max_workers}")
        self.restart()

    def perform_sync(self):
        self._log(logging.INFO, "Starting perform_sync operation (DataEntry processing).")
        try:
            processed_count = self._process_data_entries_batch()
            self._log(logging.INFO, f"perform_sync: Processed {processed_count} DataEntry items.")
            self._log(logging.INFO, "perform_sync completed successfully")

        except Exception as e:
            if PROMETHEUS_AVAILABLE:
                self.metrics_errors_total.inc()
                self.metrics_errors_by_type.labels('perform_sync').inc()
            self._log(logging.ERROR, f"Exception in perform_sync: {e}", exc_info=True)

    # Removed: add_task method. Tasks are now added directly to DB by Metabolic System.
    # def add_task(self, task_data):
    #     if not isinstance(task_data, dict):
    #         self._log(logging.ERROR, f"Attempted to add non-dict task data: {task_data}")
    #         raise ValueError("Task data must be a dictionary.")
    #     self.task_queue.put(task_data)
    #     self._log(logging.INFO, f"Added task to queue: {task_data.get('action_id', 'N/A')}")


    def health_check(self):
        status = self.status()
        metrics = {}
        if PROMETHEUS_AVAILABLE:
            metrics = {
                "cycles_total": self.metrics_cycles_total._value.get(),
                "entries_processed_total": self.metrics_entries_processed._value.get(),
                "errors_total": self.metrics_errors_total._value.get(),
                "active_workers": self.metrics_active_workers._value.get(),
            }
        return {
            "status": status,
            "metrics": metrics,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def prometheus_metrics_endpoint(self):
        if not PROMETHEUS_AVAILABLE:
            return "Prometheus client not installed", 501
        data = generate_latest()
        return (data, 200, {"Content-Type": CONTENT_TYPE_LATEST})

    def calculate_goodwill_resonance(self, goodwill_action_obj: GoodwillAction):
        self._log(logging.INFO, f"🧠 AILEE: Calculating goodwill resonance for action ID: {goodwill_action_obj.id}")

        base_score = min(100, len(goodwill_action_obj.description) / 5)

        if goodwill_action_obj.action_type == "community_support":
            base_score *= 1.2
        elif goodwill_action_obj.action_type == "environmental_contribution":
            base_score *= 1.1
        elif goodwill_action_obj.action_type == "strategic_planning":
            base_score *= 1.3
        
        raw_goodwill_score = int(min(100, max(0, base_score)))

        network_health_factor = random.uniform(0.9, 1.1)
        dignity_multiplier = 0.7

        resonance_score = int(raw_goodwill_score * network_health_factor * dignity_multiplier)
        resonance_score = min(100, max(0, resonance_score))

        self._log(logging.INFO, f"🧠 AILEE: Calculated scores for goodwill action ID {goodwill_action_obj.id} (User: {goodwill_action_obj.user_id}): Raw={raw_goodwill_score}, Resonance={resonance_score}")
        return raw_goodwill_score, resonance_score

# Example default processing plugin you can register:
def default_processing_plugin(controller, entry):
    if entry.value:
        entry.value = entry.value.upper()

# Example usage (for direct testing, not typically used when integrated with Flask)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    
    from flask import Flask as DummyFlask
    from flask_sqlalchemy import SQLAlchemy as DummySQLAlchemy
    
    dummy_app = DummyFlask(__name__)
    dummy_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    dummy_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    dummy_db = DummySQLAlchemy(dummy_app)

    with dummy_app.app_context():
        dummy_db.create_all()
        
        ailee = AILEEController.get_instance(app=dummy_app, db=dummy_db, loop_delay=2, max_workers=1)
        ailee.start()
        
        print("AILEE Controller started. Simulating DB polling...")
        # Create a dummy GoodwillAction for testing the worker
        dummy_action = GoodwillAction(
            user_id="test_user_ai", 
            action_type="strategic_planning", 
            description="This is a test description for AILEE processing.",
            timestamp=datetime.now(timezone.utc),
            status='pending' # Set status to pending for worker to pick up
        )
        dummy_db.session.add(dummy_action)
        dummy_db.session.commit()
        print(f"Added dummy GoodwillAction with ID {dummy_action.id} and status 'pending'.")
        
        try:
            while True:
                time.sleep(5)
        except KeyboardInterrupt:
            print("Stopping AILEE Controller...")
            ailee.stop()
            print("AILEE Controller stopped.")

