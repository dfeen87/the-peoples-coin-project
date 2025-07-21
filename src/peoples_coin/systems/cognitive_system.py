import os
import json
import logging
import threading
import time
from datetime import datetime, timezone
from queue import Queue, Empty
from typing import Optional, Dict, Any, Tuple

from flask import Blueprint, request, jsonify, Flask, Response
import http

from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import EventLog
from peoples_coin.extensions import db

try:
    import pika
    RABBIT_AVAILABLE = True
except ImportError:
    pika = None
    RABBIT_AVAILABLE = False

logger = logging.getLogger("cognitive_system")

class CognitiveSystem:
    """
    A resilient Cognitive System that handles event processing via a background
    thread, with graceful fallbacks and non-blocking startup.
    """

    def __init__(self):
        self.app: Optional[Flask] = None
        self.config: Dict[str, Any] = {}
        self._rabbit_connection: Optional[pika.BlockingConnection] = None
        self._in_memory_queue = Queue()

        # Threading control
        self._loop_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._initialized = False
        logger.info("🧠 Cognitive System instance created.")

    def init_app(self, app: Flask):
        """
        Configures the system from the Flask app.
        This method is safe, non-blocking, and only stores configuration.
        """
        if self._initialized:
            return

        self.app = app
        self.config = app.config

        # Set default configurations if they don't exist
        self.config.setdefault("RABBITMQ_URL", os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/"))
        self.config.setdefault("COGNITIVE_RABBIT_QUEUE", "cognitive_events")

        self._initialized = True
        logger.info("🧠 Cognitive System configured.")

    def start(self):
        """
        Starts the background processing loop. This method is non-blocking and returns instantly.
        """
        if not self._initialized:
            logger.error("🚫 Cannot start: CognitiveSystem not initialized with an app.")
            return

        if self.is_running():
            logger.warning("⚠️ CognitiveSystem background loop is already running.")
            return

        logger.info("▶️ Starting Cognitive background loop...")
        self._stop_event.clear()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True, name="CognitiveLoop")
        self._loop_thread.start()

    def stop(self):
        """
        Signals the background thread to stop gracefully.
        """
        if not self.is_running():
            logger.info("Cognitive background loop is not running.")
            return

        logger.info("🛑 Sending stop signal to cognitive background loop...")
        self._stop_event.set()

        # Give the thread a moment to shut down
        if self._loop_thread:
            self._loop_thread.join(timeout=10)

        if self.is_running():
            logger.warning("🧠 Cognitive background loop did not stop gracefully.")
        else:
            logger.info("✅ Cognitive background loop stopped.")

        # Clean up the RabbitMQ connection if it exists
        if self._rabbit_connection and self._rabbit_connection.is_open:
            self._rabbit_connection.close()

    def is_running(self) -> bool:
        """Checks if the background thread is active."""
        # 🔷 Bug Fix: Changed self.thread to self._loop_thread
        return self._loop_thread and self._loop_thread.is_alive()

    def enqueue_event(self, event: dict):
        """Adds an event to the processing queue (in-memory only)."""
        event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self._in_memory_queue.put(event)
        logger.debug(f"🧠 Event enqueued to in-memory queue: {event.get('type')}")

    def _run_loop(self):
        """
        The main resilient loop for the background thread.
        It attempts to connect to RabbitMQ and consumes from it.
        If RabbitMQ is unavailable, it processes events from the in-memory queue.
        """
        logger.info("Cognitive System background thread started.")
        while not self._stop_event.is_set():
            try:
                # First, try to process anything from RabbitMQ
                if RABBIT_AVAILABLE and self._consume_from_rabbitmq():
                    # If we processed something, continue the loop to immediately check again
                    continue

                # If RabbitMQ isn't available or had no messages, check the in-memory queue
                if self._consume_from_in_memory_queue():
                    continue

            except Exception as e:
                logger.error(f"An unexpected error occurred in the main run loop: {e}", exc_info=True)

            # If both queues were empty, wait a bit before checking again
            time.sleep(2)

        logger.info("Cognitive System background thread exiting.")

    def _get_rabbit_connection(self) -> Optional[pika.BlockingConnection]:
        """Establishes and returns a RabbitMQ connection if possible."""
        if self._rabbit_connection and self._rabbit_connection.is_open:
            return self._rabbit_connection

        try:
            logger.info("🐇 Attempting to connect to RabbitMQ...")
            params = pika.URLParameters(self.config["RABBITMQ_URL"])
            connection = pika.BlockingConnection(params)
            self._rabbit_connection = connection
            logger.info("✅ RabbitMQ connection established.")
            return connection
        except Exception as e:
            logger.warning(f"🐇 RabbitMQ connection failed: {e}")
            self._rabbit_connection = None
            return None

    def _consume_from_rabbitmq(self) -> bool:
        """Tries to consume and process one message from RabbitMQ. Returns True if a message was handled."""
        conn = self._get_rabbit_connection()
        if not conn:
            return False

        try:
            channel = conn.channel()
            channel.queue_declare(queue=self.config["COGNITIVE_RABBIT_QUEUE"], durable=True)

            # Fetch a single message without blocking forever
            method_frame, properties, body = channel.basic_get(self.config["COGNITIVE_RABBIT_QUEUE"])

            if method_frame is None:
                # No message in queue
                return False

            # We got a message, process it
            logger.info("🐇 Message received from RabbitMQ.")
            try:
                event = json.loads(body)
                self._process_event(event)
                channel.basic_ack(method_frame.delivery_tag)
            except Exception as e:
                logger.error(f"🐇 Error processing RabbitMQ message: {e}", exc_info=True)
                channel.basic_nack(method_frame.delivery_tag, requeue=True)

            return True # A message was handled

        except pika.exceptions.AMQPConnectionError as e:
            logger.warning(f"🐇 RabbitMQ connection lost: {e}")
            if self._rabbit_connection:
                self._rabbit_connection.close()
            self._rabbit_connection = None
            return False
        except Exception as e:
            logger.error(f"🐇 Unexpected error in RabbitMQ consumer: {e}", exc_info=True)
            return False


    def _consume_from_in_memory_queue(self) -> bool:
        """Tries to process one item from the in-memory queue. Returns True if an item was handled."""
        try:
            event = self._in_memory_queue.get_nowait()
            logger.info("🧠 Message received from in-memory queue.")
            self._process_event(event)
            self._in_memory_queue.task_done()
            return True
        except Empty:
            return False # No item in queue
        except Exception as e:
            logger.error(f"🧠 Error processing in-memory queue event: {e}", exc_info=True)
            return False

    def _process_event(self, event: dict):
        """The core logic for handling a single event."""
        logger.info(f"🧠 Processing cognitive event: {event.get('type')}")
        # ---
        # Implement your actual event handling logic here
        # ---
        self._persist_event(event)

    def _persist_event(self, event: dict):
        """Persists event metadata to the database."""
        if not self.app:
            return
        with self.app.app_context():
            try:
                with get_session_scope(db) as session:
                    ts_str = event.get("timestamp")
                    timestamp = datetime.fromisoformat(ts_str) if isinstance(ts_str, str) else datetime.now(timezone.utc)
                    log_entry = EventLog(
                        event_type=event.get("type", "unknown"),
                        message=f"Payload keys: {list(event.get('payload', {}).keys())}",
                        timestamp=timestamp
                    )
                    session.add(log_entry)
                    logger.debug(f"💾 Event '{event.get('type')}' persisted to EventLog.")
            except Exception as e:
                logger.error(f"💾 SQL persist error for event '{event.get('type')}': {e}", exc_info=True)


# --- Singleton Instance ---
# This single instance is imported across the application.
cognitive_system = CognitiveSystem()


# --- Flask Blueprint ---
cognitive_bp = Blueprint('cognitive_bp', __name__, url_prefix="/api/v1/cognitive")

@cognitive_bp.route('/event', methods=['POST'])
def cognitive_event() -> Tuple[Response, int]:
    """API endpoint to accept new events."""
    event = request.get_json()
    if not event or not isinstance(event, dict) or "type" not in event:
        return jsonify({"error": "Event must be a JSON object with a 'type' field."}), http.HTTPStatus.BAD_REQUEST

    # Use the in-memory queue as the entry point. The background loop will pick it up.
    cognitive_system.enqueue_event(event)

    logger.info(f"🧠 API: Event '{event.get('type')}' accepted for cognitive processing.")
    return jsonify({"message": "Event accepted for processing."}), http.HTTPStatus.ACCEPTED
