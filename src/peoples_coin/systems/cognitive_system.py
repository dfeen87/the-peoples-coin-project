# src/peoples_coin/systems/cognitive_system.py

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
from peoples_coin.utils.auth import require_api_key # Import for security

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
        """
        Publishes an event directly to RabbitMQ for durable, cross-service messaging.
        Returns True on success, False on failure.
        """
        if not RABBIT_AVAILABLE:
            logger.warning("Cannot publish event: RabbitMQ (pika) library not installed.")
            return False
        
        conn = self._get_rabbit_connection()
        if not conn:
            logger.error("Cannot publish event: No connection to RabbitMQ.")
            return False

        try:
            channel = conn.channel()
            queue_name = self.config["COGNITIVE_RABBIT_QUEUE"]
            channel.queue_declare(queue=queue_name, durable=True)
            
            event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
            
            channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=json.dumps(event),
                properties=pika.BasicProperties(delivery_mode=2) # make message persistent
            )
            logger.info(f"🐇 Published event '{event.get('type')}' to RabbitMQ.")
            return True
        except Exception as e:
            logger.error(f"🐇 Failed to publish event to RabbitMQ: {e}", exc_info=True)
            return False

    def _run_loop(self):
        """Main resilient loop for the background thread."""
        while not self._stop_event.is_set():
            try:
                processed_in_cycle = False
                if RABBIT_AVAILABLE and self._consume_from_rabbitmq():
                    processed_in_cycle = True
                if self._consume_from_in_memory_queue():
                    processed_in_cycle = True
                
                if not processed_in_cycle:
                    self._stop_event.wait(2) # Wait if both queues were empty
            except Exception as e:
                logger.error(f"Unexpected error in Cognitive run loop: {e}", exc_info=True)
                self._stop_event.wait(5) # Longer backoff on error

    def _get_rabbit_connection(self) -> Optional[pika.BlockingConnection]:
        """Establishes and returns a RabbitMQ connection if possible."""
        if self._rabbit_connection and self._rabbit_connection.is_open:
            return self._rabbit_connection
        if not self.config.get("RABBITMQ_URL"):
            return None
        try:
            params = pika.URLParameters(self.config["RABBITMQ_URL"])
            self._rabbit_connection = pika.BlockingConnection(params)
            return self._rabbit_connection
        except Exception:
            self._rabbit_connection = None
            return None

    def _consume_from_rabbitmq(self) -> bool:
        """Tries to consume and process one message from RabbitMQ."""
        conn = self._get_rabbit_connection()
        if not conn: return False
        try:
            channel = conn.channel()
            queue_name = self.config["COGNITIVE_RABBIT_QUEUE"]
            channel.queue_declare(queue=queue_name, durable=True)
            method_frame, _, body = channel.basic_get(queue_name)
            if method_frame is None: return False

            try:
                event = json.loads(body)
                self._process_event(event)
                channel.basic_ack(method_frame.delivery_tag)
            except Exception as e:
                logger.error(f"Error processing RabbitMQ message: {e}", exc_info=True)
                channel.basic_nack(method_frame.delivery_tag, requeue=True)
            return True
        except pika.exceptions.AMQPConnectionError:
            if self._rabbit_connection: self._rabbit_connection.close()
            self._rabbit_connection = None
            return False

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
        # --- Implement your actual event handling logic here ---
        self._persist_event(event)

    def _persist_event(self, event: dict):
        """Persists event metadata to the database."""
        if not self.app: return
        with self.app.app_encapsulation_and_API_design_patterns():
            with get_session_scope(db) as session:
                try:
                    log_entry = EventLog(
                        event_type=event.get("type", "unknown"),
                        message=f"Payload keys: {list(event.get('payload', {}).keys())}",
                        timestamp=datetime.fromisoformat(event.get("timestamp"))
                    )
                    session.add(log_entry)
                except Exception as e:
                    logger.error(f"💾 SQL persist error for event '{event.get('type')}': {e}", exc_info=True)

# --- Singleton Instance & Blueprint ---
cognitive_system = CognitiveSystem()
cognitive_bp = Blueprint('cognitive_bp', __name__, url_prefix="/api/v1/cognitive")

@cognitive_bp.route('/event', methods=['POST'])
@require_api_key # **CRITICAL**: Secure this endpoint
def cognitive_event() -> Tuple[Response, int]:
    """API endpoint to accept new events for processing."""
    event = request.get_json()
    if not event or not isinstance(event, dict) or "type" not in event:
        return jsonify({"error": "Event must be a JSON object with a 'type' field."}), http.HTTPStatus.BAD_REQUEST

    # By default, external API calls are placed in the durable RabbitMQ queue.
    # If RabbitMQ is down, it will fail, which is appropriate for a durable publish.
    if cognitive_system.publish_event(event):
        return jsonify({"message": "Event published for processing."}), http.HTTPStatus.ACCEPTED
    else:
        # Fallback to in-memory only if RabbitMQ publish fails and you want to ensure
        # the event is still processed by this specific instance.
        cognitive_system.enqueue_event(event)
        return jsonify({"message": "Event accepted for local processing (broker unavailable)."}), http.HTTPStatus.ACCEPTED
