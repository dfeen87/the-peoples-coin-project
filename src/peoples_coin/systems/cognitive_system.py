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
from peoples_coin.extensions import db  # 🔷 Fix: import db explicitly

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

# Default RabbitMQ URL and queue — update as needed or via environment variables
DEFAULT_RABBITMQ_URL = os.getenv(
    "COGNITIVE_RABBITMQ_URL",
    "amqp://myuser:JmTa1tvVHcG3UB9F@rabbitmq.default.svc.cluster.local:5672/"
)
DEFAULT_RABBITMQ_QUEUE = os.getenv("COGNITIVE_RABBIT_QUEUE", "cognitive_events")


class CognitiveSystem:
    """
    Cognitive System — handles event processing with support for RabbitMQ, Firestore, and DB persistence.
    """

    def __init__(self):
        self.app: Optional[Flask] = None
        self.config: Dict[str, Any] = {}
        self.firestore_client: Optional[firestore.Client] = None
        self._stop_event = threading.Event()
        self._loop_thread: Optional[threading.Thread] = None
        self._in_memory_queue = Queue()
        self._initialized = False
        self._rabbit_connection: Optional[pika.BlockingConnection] = None
        logger.info("🧠 Cognitive System instance created.")

    def init_app(self, app: Flask):
        if self._initialized:
            return
        self.app = app
        self.config = app.config
        self.config.setdefault("COGNITIVE_LOOP_DELAY", 5.0)
        self.config.setdefault("COGNITIVE_RABBITMQ_URL", DEFAULT_RABBITMQ_URL)
        self.config.setdefault("COGNITIVE_RABBIT_QUEUE", DEFAULT_RABBITMQ_QUEUE)

        self._initialize_firestore_client()
        self._initialized = True
        logger.info(f"🧠 Cognitive System initialized. RabbitMQ → {self.config['COGNITIVE_RABBITMQ_URL']}")

    def _initialize_firestore_client(self):
        if GCP_AVAILABLE and not self.firestore_client:
            try:
                self.firestore_client = firestore.Client()
                logger.info("☁️ Google Cloud Firestore client initialized.")
            except Exception as e:
                logger.warning(f"☁️ Firestore init failed: {e}. Firestore features disabled.")
                self.firestore_client = None

    def _get_rabbit_connection(self, max_retries: int = 5, retry_delay: int = 5) -> Optional[pika.BlockingConnection]:
        # Return cached connection if still open
        if self._rabbit_connection and self._rabbit_connection.is_open:
            return self._rabbit_connection

        for attempt in range(1, max_retries + 1):
            try:
                params = pika.URLParameters(self.config["COGNITIVE_RABBITMQ_URL"])
                connection = pika.BlockingConnection(params)
                self._rabbit_connection = connection
                logger.info(f"🐇 RabbitMQ connection established on attempt {attempt}.")
                return connection
            except pika.exceptions.AMQPConnectionError as e:
                logger.warning(f"🐇 RabbitMQ connection attempt {attempt}/{max_retries} failed: {e}")
                time.sleep(retry_delay)
            except Exception as e:
                logger.warning(f"🐇 RabbitMQ unexpected error on attempt {attempt}/{max_retries}: {e}")
                time.sleep(retry_delay)

        logger.error("🐇 RabbitMQ connection failed after max retries — using in-memory queue.")
        self._rabbit_connection = None
        return None

    def enqueue_event(self, event: dict):
        event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        if RABBIT_AVAILABLE:
            connection = self._get_rabbit_connection()
            if connection:
                try:
                    channel = connection.channel()
                    channel.queue_declare(queue=self.config["COGNITIVE_RABBIT_QUEUE"], durable=True)
                    channel.basic_publish(
                        exchange='',
                        routing_key=self.config["COGNITIVE_RABBIT_QUEUE"],
                        body=json.dumps(event),
                        properties=pika.BasicProperties(delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE)
                    )
                    logger.debug(f"🐇 Event enqueued to RabbitMQ: {event.get('type')}")
                    return
                except Exception as e:
                    logger.warning(f"🐇 RabbitMQ publish failed: {e}, falling back to in-memory queue.")
                    # Close faulty connection to force reconnect later
                    try:
                        if self._rabbit_connection:
                            self._rabbit_connection.close()
                    except Exception:
                        pass
                    self._rabbit_connection = None
            else:
                logger.info("🐇 RabbitMQ connection unavailable, using in-memory queue.")
        self._in_memory_queue.put(event)
        logger.debug(f"🧠 Event enqueued to in-memory queue: {event.get('type')}")

    def start_background_loop(self):
        if not self._initialized:
            logger.error("🚫 Cannot start: CognitiveSystem not initialized.")
            return
        if self.is_running():
            logger.warning("⚠️ CognitiveSystem already running.")
            return

        self._stop_event.clear()
        logger.info("▶️ Starting Cognitive background loop...")

        connection = self._get_rabbit_connection()
        if RABBIT_AVAILABLE and connection:
            logger.info("🐇 Using RabbitMQ consumer loop.")
            target = self._rabbit_consumer_loop
        else:
            logger.info("🧠 Using in-memory consumer loop.")
            target = self._in_memory_consumer_loop

        self._loop_thread = threading.Thread(target=target, daemon=True, name="CognitiveLoop")
        self._loop_thread.start()
        logger.info("🧠 Cognitive background loop started.")

    def stop_background_loop(self):
        if self._loop_thread and self._loop_thread.is_alive():
            logger.info("🧠 Sending stop signal to cognitive background loop...")
            self._stop_event.set()
            self._loop_thread.join(timeout=10)
            if self._loop_thread.is_alive():
                logger.warning("🧠 Cognitive background loop did not stop gracefully.")
            else:
                logger.info("🧠 Cognitive background loop stopped.")

    def is_running(self) -> bool:
        return self._loop_thread is not None and self._loop_thread.is_alive()

    def _persist_event(self, event: dict):
        if not self.app:
            logger.error("💾 Cannot persist event: app context is not set.")
            return
        with self.app.app_context():
            try:
                with get_session_scope(db) as session:
                    ts = event.get("timestamp")
                    timestamp = datetime.fromisoformat(ts) if isinstance(ts, str) else datetime.now(timezone.utc)
                    ev = EventLog(
                        event_type=event.get("type", "unknown"),
                        message=f"Payload keys: {list(event.get('payload', {}).keys()) if 'payload' in event else 'none'}",
                        timestamp=timestamp
                    )
                    session.add(ev)
                    logger.debug(f"💾 Event '{event.get('type')}' persisted to EventLog.")
            except Exception as e:
                logger.error(f"💾 SQL persist error for event '{event.get('type')}': {e}", exc_info=True)

    def _in_memory_consumer_loop(self):
        logger.info("🧠 In-memory cognitive consumer loop started.")
        while not self._stop_event.is_set():
            try:
                event = self._in_memory_queue.get(timeout=self.config["COGNITIVE_LOOP_DELAY"])
                self._process_event(event)
                self._in_memory_queue.task_done()
            except Empty:
                continue
            except Exception as e:
                logger.error(f"🧠 Error in in-memory consumer loop: {e}", exc_info=True)
        logger.info("🧠 In-memory cognitive consumer loop exiting.")

    def _rabbit_consumer_loop(self):
        logger.info("🐇 RabbitMQ cognitive consumer loop started.")
        while not self._stop_event.is_set():
            connection = self._get_rabbit_connection(max_retries=3, retry_delay=10)
            if not connection:
                if self._stop_event.wait(timeout=30):
                    break
                continue
            try:
                channel = connection.channel()
                channel.queue_declare(queue=self.config["COGNITIVE_RABBIT_QUEUE"], durable=True)
                for method_frame, properties, body in channel.consume(self.config["COGNITIVE_RABBIT_QUEUE"]):
                    if self._stop_event.is_set():
                        channel.basic_nack(method_frame.delivery_tag, requeue=True)
                        break
                    try:
                        event = json.loads(body)
                        self._process_event(event)
                        channel.basic_ack(method_frame.delivery_tag)
                    except Exception as e:
                        logger.error(f"🐇 Error processing RabbitMQ message: {e}", exc_info=True)
                        channel.basic_nack(method_frame.delivery_tag, requeue=True)
                        time.sleep(5)
                channel.cancel()
                connection.close()
                self._rabbit_connection = None
            except pika.exceptions.AMQPConnectionError as e:
                logger.warning(f"🐇 RabbitMQ consumer connection lost: {e}, retrying...")
                if self._stop_event.wait(timeout=10):
                    break
                self._rabbit_connection = None
            except Exception as e:
                logger.error(f"🐇 Unexpected error in RabbitMQ consumer loop: {e}", exc_info=True)
                if self._stop_event.wait(timeout=10):
                    break
                self._rabbit_connection = None

    def _process_event(self, event: dict):
        logger.info(f"🧠 Processing cognitive event: {event.get('type')}")
        # Implement your cognitive event handling logic here
        self._persist_event(event)


# Singleton instance for import and usage
cognitive_system = CognitiveSystem()


# Helper functions for run.py and elsewhere
def register_cognitive_system(app: Flask):
    cognitive_system.init_app(app)

def start_thought_loop():
    cognitive_system.start_background_loop()

def stop_thought_loop():
    cognitive_system.stop_background_loop()

_thought_loop_running = property(lambda: cognitive_system.is_running())


# Flask Blueprint for cognitive endpoints
cognitive_bp = Blueprint('cognitive_bp', __name__, url_prefix="/api/v1/cognitive")


@cognitive_bp.route('/event', methods=['POST'])
def cognitive_event() -> Tuple[Response, int]:
    event = request.get_json()
    if not event or not isinstance(event, dict) or "type" not in event:
        return jsonify({"error": "Event must be a JSON object with a 'type' field."}), http.HTTPStatus.BAD_REQUEST

    cognitive_system.enqueue_event(event)
    logger.info(f"🧠 API: Event '{event.get('type')}' accepted for cognitive processing.")
    return jsonify({"message": "Event accepted for processing."}), http.HTTPStatus.ACCEPTED

