# peoples_coin/systems/cognitive_system.py

import os
import json
import logging
import threading
import time
from datetime import datetime, timezone
from queue import Queue, Empty
from typing import Optional, Dict, Any

from flask import Flask

from peoples_coin.models.db_utils import get_session_scope
# CORRECTED: Import AuditLog, which exists in your final schema
from peoples_coin.models.models import AuditLog
from peoples_coin.extensions import db

try:
    import pika
    RABBIT_AVAILABLE = True
except ImportError:
    pika = None
    RABBIT_AVAILABLE = False

logger = logging.getLogger("cognitive_system")

class CognitiveSystem:
    """A resilient event processing system with RabbitMQ and in-memory fallbacks."""

    def __init__(self):
        self.app: Optional[Flask] = None
        self.config: Dict[str, Any] = {}
        self._rabbit_connection: Optional[pika.BlockingConnection] = None
        self._in_memory_queue = Queue()
        self._loop_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._initialized = False
        logger.info("🧠 Cognitive System instance created.")

    def init_app(self, app: Flask):
        """Configures the system from the Flask app in a non-blocking way."""
        if self._initialized:
            return
        self.app = app
        self.config = app.config
        self.config.setdefault("RABBITMQ_URL", os.getenv("RABBITMQ_URL"))
        self.config.setdefault("COGNITIVE_RABBIT_QUEUE", "cognitive_events")
        self._initialized = True
        logger.info("🧠 Cognitive System configured.")

    def start(self):
        """Starts the background processing loop thread."""
        if not self._initialized:
            raise RuntimeError("Cannot start: CognitiveSystem not initialized.")
        if self.is_running():
            return
        logger.info("▶️ Starting Cognitive background loop...")
        self._stop_event.clear()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True, name="CognitiveLoop")
        self._loop_thread.start()

    def stop(self):
        """Signals the background thread to stop gracefully."""
        if self.is_running():
            logger.info("🛑 Sending stop signal to cognitive background loop...")
            self._stop_event.set()
            if self._loop_thread:
                self._loop_thread.join(timeout=10)
            if self._rabbit_connection and self._rabbit_connection.is_open:
                self._rabbit_connection.close()
            logger.info("✅ Cognitive background loop stopped.")

    def is_running(self) -> bool:
        """Checks if the background thread is active."""
        return self._loop_thread and self._loop_thread.is_alive()

    def enqueue_event(self, event: dict):
        """Adds an event to the internal, in-memory processing queue."""
        event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self._in_memory_queue.put(event)

    def publish_event(self, event: dict) -> bool:
        """Publishes an event directly to RabbitMQ for durable messaging."""
        # ... (This method can remain as is)
        pass

    def _run_loop(self):
        """Main loop for the background thread."""
        while not self._stop_event.is_set():
            try:
                processed = self._consume_from_in_memory_queue()
                if not processed:
                    self._stop_event.wait(2)
            except Exception as e:
                logger.error(f"Unexpected error in Cognitive run loop: {e}", exc_info=True)
                self._stop_event.wait(5)

    def _get_rabbit_connection(self) -> Optional[pika.BlockingConnection]:
        # ... (This method can remain as is)
        pass

    def _consume_from_in_memory_queue(self) -> bool:
        """Tries to process one item from the in-memory queue."""
        try:
            event = self._in_memory_queue.get_nowait()
            self._process_event(event)
            self._in_memory_queue.task_done()
            return True
        except Empty:
            return False

    def _process_event(self, event: dict):
        """The core logic for handling a single event."""
        logger.info(f"🧠 Processing cognitive event: {event.get('type')}")
        self._persist_event(event)

    def _persist_event(self, event: dict):
        """Persists event metadata to the database using the AuditLog table."""
        if not self.app: return
        with self.app.app_context():
            with get_session_scope(db) as session:
                try:
                    # CORRECTED: Create an AuditLog object instead of EventLog
                    log_entry = AuditLog(
                        action_type=event.get("type", "unknown"),
                        details={
                            "message": f"Payload keys: {list(event.get('payload', {}).keys())}",
                            "source": event.get("source")
                        }
                    )
                    session.add(log_entry)
                except Exception as e:
                    logger.error(f"💾 SQL persist error: {e}", exc_info=True)


# Singleton instance
cognitive_system = CognitiveSystem()

# --- Functions for status page ---

def get_cognitive_status():
    """Health check for the Cognitive System."""
    if cognitive_system._initialized and cognitive_system.is_running():
        return {"active": True, "healthy": True, "info": "Cognitive System operational"}
    else:
        return {"active": False, "healthy": False, "info": "Cognitive System not initialized or not running"}

def get_cognitive_transaction_state(txn_id: str):
    """Placeholder for checking a transaction's cognitive state."""
    return {"state": "governance-approved", "confirmed": True}
