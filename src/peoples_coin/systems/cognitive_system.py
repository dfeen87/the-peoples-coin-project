import os
import json
import logging
import threading
import time
from datetime import datetime
from queue import Queue, Empty
from typing import Optional

from flask import Blueprint, request, jsonify, Flask, current_app

# Assuming these utilities exist from previous files
from ..db.db_utils import get_session_scope
from ..db.models import CognitiveEvent

# Conditionally import optional dependencies
try:
    import pika
    RABBIT_AVAILABLE = True
except ImportError:
    pika = None
    RABBIT_AVAILABLE = False

try:
    from google.cloud import firestore
    GCP_AVAILABLE = True
except ImportError:
    firestore = None
    GCP_AVAILABLE = False

logger = logging.getLogger("cognitive_system")

class CognitiveSystem:
    """
    A resilient event processing system with a background worker, message queue
    (RabbitMQ with in-memory fallback), and multi-backend persistence.
    """

    def __init__(self):
        self.app: Optional[Flask] = None
        self.config = {}
        
        # External clients
        self.firestore_client: Optional[firestore.Client] = None
        
        # State and concurrency
        self._stop_event = threading.Event()
        self._loop_thread: Optional[threading.Thread] = None
        self._in_memory_queue = Queue()
        self._initialized = False

    def init_app(self, app: Flask):
        """Initializes the Cognitive System with the Flask app context."""
        if self._initialized:
            return
        
        self.app = app
        self.config = app.config
        
        # Default config values
        self.config.setdefault("COGNITIVE_LOOP_DELAY", 5.0)
        self.config.setdefault("COGNITIVE_REFLECTION_INTERVAL", 30.0)
        self.config.setdefault("COGNITIVE_RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
        self.config.setdefault("COGNITIVE_RABBIT_QUEUE", "cognitive_events")
        self.config.setdefault("COGNITIVE_FIRESTORE_COLLECTION", "cognitive_memory")

        self._initialize_firestore_client()
        self.start_background_loop()
        self._initialized = True
        logger.info("🧠 Cognitive System initialized.")

    def _initialize_firestore_client(self):
        """Initializes the Firestore client if GCP is available."""
        if GCP_AVAILABLE and not self.firestore_client:
            try:
                self.firestore_client = firestore.Client()
                logger.info("☁️ Google Cloud Firestore client initialized.")
            except Exception as e:
                logger.warning(f"☁️ Google Cloud Firestore client failed to initialize: {e}")
                self.firestore_client = None

    # --- Public Methods ---

    def enqueue_event(self, event: dict):
        """
        Enqueues an event for processing, preferring RabbitMQ if available.
        """
        # Add a default timestamp if not present
        event.setdefault("timestamp", datetime.utcnow().isoformat())

        if RABBIT_AVAILABLE:
            try:
                # For web requests, short-lived connections are simpler than pooling.
                # In very high-throughput scenarios, a connection pool (e.g., kombu) would be better.
                params = pika.URLParameters(self.config["COGNITIVE_RABBITMQ_URL"])
                with pika.BlockingConnection(params) as conn:
                    ch = conn.channel()
                    ch.queue_declare(queue=self.config["COGNITIVE_RABBIT_QUEUE"], durable=True)
                    ch.basic_publish(
                        exchange='',
                        routing_key=self.config["COGNITIVE_RABBIT_QUEUE"],
                        body=json.dumps(event),
                        properties=pika.BasicProperties(delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE)
                    )
                logger.info(f"🐇 Event enqueued to RabbitMQ: {event.get('type')}")
                return
            except pika.exceptions.AMQPConnectionError as e:
                logger.warning(f"🐇 RabbitMQ connection failed ({e}), falling back to in-memory queue.")
        
        self._in_memory_queue.put(event)
        logger.info(f"🧠 Event enqueued (in-memory): {event.get('type')}")

    def start_background_loop(self):
        """Starts the main background worker thread."""
        if not self._loop_thread or not self._loop_thread.is_alive():
            self._stop_event.clear()
            target_loop = self._rabbit_consumer_loop if RABBIT_AVAILABLE else self._in_memory_consumer_loop
            self._loop_thread = threading.Thread(target=target_loop, daemon=True, name="CognitiveLoop")
            self._loop_thread.start()
            logger.info("🧠 Cognitive background loop started.")

    def stop_background_loop(self):
        """Signals the background worker to stop and waits for it to exit."""
        if self._loop_thread and self._loop_thread.is_alive():
            logger.info("🧠 Sending stop signal to cognitive background loop...")
            self._stop_event.set()
            self._loop_thread.join(timeout=10)
            if self._loop_thread.is_alive():
                logger.warning("🧠 Cognitive loop did not exit gracefully.")
            else:
                logger.info("🧠 Cognitive background loop stopped.")

    # --- Core Logic & Background Loops ---

    def _persist_event(self, event: dict):
        """Persists a single event to both SQL and Firestore."""
        with self.app.app_context():
            # Persist to SQL DB
            try:
                with get_session_scope() as session:
                    ev = CognitiveEvent(
                        event_type=event.get("type", "unknown"),
                        payload=json.dumps(event.get("payload", {})),
                        timestamp=datetime.fromisoformat(event.get("timestamp"))
                    )
                    session.add(ev)
                logger.info(f"💾 Event persisted in database: {ev.event_type}")
            except Exception as e:
                logger.error(f"💾 SQL persist error: {e}", exc_info=True)

            # Persist to Firestore
            if self.firestore_client:
                try:
                    doc_ref = self.firestore_client.collection(self.config["COGNITIVE_FIRESTORE_COLLECTION"]).document()
                    doc_ref.set(event)
                    logger.debug(f"☁️ Event persisted to Firestore: {event.get('type')}")
                except Exception as e:
                    logger.error(f"☁️ Firestore persist error: {e}")

    def _in_memory_consumer_loop(self):
        """Worker loop for processing events from the in-memory queue."""
        logger.info("🧠 Starting in-memory queue consumer loop.")
        while not self._stop_event.is_set():
            try:
                event = self._in_memory_queue.get(timeout=self.config["COGNITIVE_LOOP_DELAY"])
                self._persist_event(event)
                self._in_memory_queue.task_done()
            except Empty:
                continue # No events, loop will check stop_event
            except Exception as e:
                logger.error(f"🧠 Error in in-memory loop: {e}", exc_info=True)
                time.sleep(5)

    def _rabbit_consumer_loop(self):
        """Worker loop for consuming events from RabbitMQ with reconnect logic."""
        logger.info("🐇 Starting RabbitMQ consumer loop.")
        while not self._stop_event.is_set():
            try:
                params = pika.URLParameters(self.config["COGNITIVE_RABBITMQ_URL"])
                connection = pika.BlockingConnection(params)
                channel = connection.channel()
                channel.queue_declare(queue=self.config["COGNITIVE_RABBIT_QUEUE"], durable=True)
                
                logger.info("🐇 Consumer connected, waiting for messages...")
                for method_frame, properties, body in channel.consume(self.config["COGNITIVE_RABBIT_QUEUE"]):
                    if self._stop_event.is_set():
                        break
                    try:
                        event = json.loads(body)
                        self._persist_event(event)
                        channel.basic_ack(method_frame.delivery_tag)
                    except json.JSONDecodeError:
                        logger.error("🐇 Failed to decode message body. Discarding.")
                        channel.basic_nack(method_frame.delivery_tag, requeue=False)
                    except Exception as e:
                        logger.error(f"🐇 Error processing message: {e}. Re-queueing.")
                        channel.basic_nack(method_frame.delivery_tag, requeue=True)
                        # To prevent rapid re-processing of a poison pill message
                        time.sleep(5)

                channel.cancel()
                connection.close()
                logger.info("🐇 Consumer loop finished gracefully.")

            except pika.exceptions.AMQPConnectionError as e:
                logger.error(f"🐇 Consumer connection failed: {e}. Retrying in 10 seconds...")
                self._stop_event.wait(10)
            except Exception as e:
                logger.error(f"🐇 Unhandled error in consumer loop: {e}", exc_info=True)
                self._stop_event.wait(10)

# --- Blueprint and Routes ---
cognitive_bp = Blueprint('cognitive_bp', __name__)

@cognitive_bp.route('/cognitive/status', methods=['GET'])
def cognitive_status():
    from . import cognitive_system # Local import to access instance
    pending_events = "N/A (Using RabbitMQ)"
    if not RABBIT_AVAILABLE:
        pending_events = cognitive_system._in_memory_queue.qsize()

    return jsonify({
        "status": "running" if cognitive_system._loop_thread.is_alive() else "stopped",
        "event_queue_backend": "RabbitMQ" if RABBIT_AVAILABLE else "In-Memory",
        "pending_events_in_memory": pending_events,
    })

@cognitive_bp.route('/cognitive/event', methods=['POST'])
def cognitive_event():
    from . import cognitive_system # Local import to access instance
    event = request.get_json()
    if not event or not isinstance(event, dict) or "type" not in event:
        return jsonify({"error": "Event must be a JSON object with a 'type' field."}), http.HTTPStatus.BAD_REQUEST

    cognitive_system.enqueue_event(event)
    return jsonify({"message": "Event accepted for processing."}), http.HTTPStatus.ACCEPTED

