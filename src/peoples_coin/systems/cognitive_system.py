import os
import json
import logging
import threading
import time
from datetime import datetime, timezone
from queue import Queue, Empty
from typing import Optional, Dict, Any

from flask import Blueprint, request, jsonify, Flask, Response
import http

from peoples_coin.db.db_utils import get_session_scope
from peoples_coin.db.models import EventLog # EventLog will be used here

# Conditional imports for message queuing and Firestore
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
    firestore_client = None # Explicitly set to None
    GCP_AVAILABLE = False

logger = logging.getLogger("cognitive_system")

class CognitiveSystem:
    def __init__(self):
        self.app: Optional[Flask] = None
        self.config: Dict = {}
        self.firestore_client: Optional[firestore.Client] = None
        self._stop_event = threading.Event()
        self._loop_thread: Optional[threading.Thread] = None
        self._in_memory_queue = Queue()
        self._initialized = False
        logger.info("🧠 Cognitive System instance created.")

    def init_app(self, app: Flask):
        if self._initialized:
            return
        
        self.app = app
        self.config = app.config
        self.config.setdefault("COGNITIVE_LOOP_DELAY", 5.0)
        self.config.setdefault("COGNITIVE_RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
        self.config.setdefault("COGNITIVE_RABBIT_QUEUE", "cognitive_events")
        
        self._initialize_firestore_client()
        self._initialized = True
        logger.info("🧠 Cognitive System initialized and ready to start.")
        # Note: start_background_loop() should be called explicitly from run.py or app startup code.
        # For Cloud Run, background loops should typically run in separate worker services.

    def _initialize_firestore_client(self):
        """Initializes Google Cloud Firestore client."""
        if GCP_AVAILABLE and not self.firestore_client:
            try:
                # Ensure GOOGLE_APPLICATION_CREDENTIALS or default credentials are set up
                # Service account running Cloud Run needs 'Cloud Datastore User' role at least.
                self.firestore_client = firestore.Client()
                logger.info("☁️ Google Cloud Firestore client initialized.")
            except Exception as e:
                logger.warning(f"☁️ Google Cloud Firestore client failed to initialize: {e}. Firestore features may be unavailable.")
                self.firestore_client = None

    def _get_rabbit_connection(self, max_retries=5, retry_delay=5):
        """Attempts to establish a RabbitMQ connection with retries."""
        for attempt in range(max_retries):
            try:
                params = pika.URLParameters(self.config["COGNITIVE_RABBITMQ_URL"])
                connection = pika.BlockingConnection(params)
                logger.debug(f"🐇 RabbitMQ connection established on attempt {attempt + 1}.")
                return connection
            except pika.exceptions.AMQPConnectionError as e:
                logger.warning(f"🐇 RabbitMQ connection attempt {attempt + 1} failed: {e}")
                time.sleep(retry_delay)
        logger.error("🐇 RabbitMQ connection failed after max retries, falling back to in-memory queue.")
        return None

    def enqueue_event(self, event: dict):
        """
        Enqueues an event for asynchronous processing.
        Attempts to use RabbitMQ, falls back to in-memory queue.
        """
        event.setdefault("timestamp", datetime.now(timezone.utc).isoformat()) # Use timezone.utc for consistency
        if RABBIT_AVAILABLE:
            connection = self._get_rabbit_connection()
            if connection:
                try:
                    ch = connection.channel()
                    ch.queue_declare(queue=self.config["COGNITIVE_RABBIT_QUEUE"], durable=True)
                    ch.basic_publish(
                        exchange='',
                        routing_key=self.config["COGNITIVE_RABBIT_QUEUE"],
                        body=json.dumps(event),
                        properties=pika.BasicProperties(delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE)
                    )
                    connection.close()
                    logger.debug(f"🐇 Event enqueued to RabbitMQ: {event.get('type')}")
                    return
                except Exception as e:
                    logger.warning(f"🐇 RabbitMQ publish failed: {e}, falling back to in-memory.")
            else:
                logger.info("🐇 RabbitMQ connection unavailable, using in-memory queue.")
        self._in_memory_queue.put(event)
        logger.debug(f"🧠 Event enqueued to in-memory queue: {event.get('type')}")


    def start_background_loop(self):
        """
        Starts the background consumer loop for cognitive events.
        For Cloud Run, this loop should ideally run in a separate worker service.
        """
        if not self._initialized:
            logger.error("🚫 Cannot start: CognitiveSystem not initialized.")
            return

        if self.is_running():
            logger.warning("⚠️ CognitiveSystem already running.")
            return

        logger.info("▶️ Starting Cognitive background loop...")
        self._stop_event.clear()
        target_loop = self._rabbit_consumer_loop if RABBIT_AVAILABLE else self._in_memory_consumer_loop
        self._loop_thread = threading.Thread(target=target_loop, daemon=True, name="CognitiveLoop")
        self._loop_thread.start()
        logger.info("🧠 Cognitive background loop started.")

    def stop_background_loop(self):
        """Stops the background consumer loop gracefully."""
        if self._loop_thread and self._loop_thread.is_alive():
            logger.info("🧠 Sending stop signal to cognitive background loop...")
            self._stop_event.set()
            self._loop_thread.join(timeout=10) # Give it 10 seconds to join
            if self._loop_thread.is_alive():
                logger.warning("🧠 Cognitive background loop did not stop gracefully.")
            logger.info("🧠 Cognitive background loop stopped.")

    def is_running(self) -> bool:
        """Checks if the background consumer loop is active."""
        return self._loop_thread is not None and self._loop_thread.is_alive()

    def _persist_event(self, event: dict):
        """Persists a processed event to the EventLog database table."""
        with self.app.app_context(): # Ensure app context for DB operations
            try:
                with get_session_scope(db) as session:
                    # Ensure timestamp is a datetime object
                    event_timestamp = datetime.fromisoformat(event.get("timestamp")) if isinstance(event.get("timestamp"), str) else datetime.now(timezone.utc)
                    
                    ev = EventLog(
                        event_type=event.get("type", "unknown"),
                        message=f"Event payload keys: {list(event.get('payload', {}).keys())}",
                        timestamp=event_timestamp # Use the event's timestamp
                    )
                    session.add(ev)
                    logger.debug(f"💾 Event '{event.get('type')}' persisted to EventLog.")
            except Exception as e:
                logger.error(f"💾 SQL persist error for event '{event.get('type')}': {e}", exc_info=True)

    def _in_memory_consumer_loop(self):
        """Consumer loop for events from the in-memory queue."""
        logger.info("🧠 In-memory cognitive consumer loop started.")
        while not self._stop_event.is_set():
            try:
                # Get event with a timeout to allow checking stop_event
                event = self._in_memory_queue.get(timeout=self.config["COGNITIVE_LOOP_DELAY"])
                self._process_event(event) # Process the event
                self._in_memory_queue.task_done()
            except Empty:
                # Queue was empty, continue loop
                continue
            except Exception as e:
                logger.error(f"🧠 Error in in-memory consumer loop: {e}", exc_info=True)
        logger.info("🧠 In-memory cognitive consumer loop exiting.")

    def _rabbit_consumer_loop(self):
        """Consumer loop for events from RabbitMQ."""
        logger.info("🐇 RabbitMQ cognitive consumer loop started.")
        while not self._stop_event.is_set():
            connection = self._get_rabbit_connection(max_retries=3, retry_delay=10)
            if not connection:
                if self._stop_event.wait(timeout=30): # Wait and check stop event
                    break
                continue
            try:
                channel = connection.channel()
                channel.queue_declare(queue=self.config["COGNITIVE_RABBIT_QUEUE"], durable=True)
                # Use pika's consumer_iter for graceful shutdown
                for method_frame, properties, body in channel.consume(self.config["COGNITIVE_RABBIT_QUEUE"]):
                    if self._stop_event.is_set():
                        # If stop signal received, nack the current message and break
                        channel.basic_nack(method_frame.delivery_tag, requeue=True)
                        break
                    try:
                        event = json.loads(body)
                        self._process_event(event) # Process the event
                        channel.basic_ack(method_frame.delivery_tag)
                    except Exception as e:
                        logger.error(f"🐇 Error processing RabbitMQ message: {e}", exc_info=True)
                        channel.basic_nack(method_frame.delivery_tag, requeue=True) # Nack and requeue on error
                        time.sleep(5) # Small delay to prevent tight loop on persistent error
                
                # If consume loop breaks (e.g., stop_event), ensure connection is closed
                channel.cancel()
                connection.close()
            except pika.exceptions.AMQPConnectionError as e:
                logger.warning(f"🐇 RabbitMQ consumer connection lost: {e}, retrying...")
                if self._stop_event.wait(timeout=10): # Wait and check stop event
                    break
            except Exception as e:
                logger.error(f"🐇 Unexpected error in RabbitMQ consumer loop: {e}", exc_info=True)
                if self._stop_event.wait(timeout=10):
                    break

    def _process_event(self, event: dict):
        """
        Main event processing logic for the Cognitive System.
        This is where you'd implement the 'learning from and reflecting upon network-wide information'.
        """
        logger.info(f"🧠 Processing cognitive event: {event.get('type')}")
        # Example:
        # if event.get('type') == 'goodwill_action_processed':
        #     # Analyze goodwill action, update user reputation, etc.
        #     pass
        # elif event.get('type') == 'block_mined':
        #     # Analyze block data, update chain stats, etc.
        #     pass
        # Persist event to DB
        self._persist_event(event)


cognitive_bp = Blueprint('cognitive_bp', __name__, url_prefix="/api/v1/cognitive") # Added url_prefix

@cognitive_bp.route('/event', methods=['POST'])
def cognitive_event() -> Tuple[Response, int]:
    from ..extensions import cognitive_system # Import the singleton instance
    event = request.get_json()
    if not event or not isinstance(event, dict) or "type" not in event:
        return jsonify({"error": "Event must be a JSON object with a 'type' field."}), http.HTTPStatus.BAD_REQUEST
    
    # Enqueue event for asynchronous processing by the CognitiveSystem's background loop
    cognitive_system.enqueue_event(event)
    logger.info(f"🧠 API: Event '{event.get('type')}' accepted for cognitive processing.")
    return jsonify({"message": "Event accepted for processing."}), http.HTTPStatus.ACCEPTED

# Singleton instance of CognitiveSystem
cognitive_system = CognitiveSystem()
