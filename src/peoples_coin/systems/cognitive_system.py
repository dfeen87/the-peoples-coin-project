import os
import json
import logging
import threading
import time
from datetime import datetime
from queue import Queue, Empty
from typing import Optional, Dict

from flask import Blueprint, request, jsonify, Flask, Response
import http

from ..db.db_utils import get_session_scope
from ..db.models import EventLog

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
    def __init__(self):
        self.app: Optional[Flask] = None
        self.config: Dict = {}
        self.firestore_client: Optional[firestore.Client] = None
        self._stop_event = threading.Event()
        self._loop_thread: Optional[threading.Thread] = None
        self._in_memory_queue = Queue()
        self._initialized = False

    def init_app(self, app: Flask):
        """Initializes the Cognitive System but does NOT start the background loop."""
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
        # NOTE: start_background_loop() is now called explicitly from run.py

    def _initialize_firestore_client(self):
        if GCP_AVAILABLE and not self.firestore_client:
            try:
                self.firestore_client = firestore.Client()
                logger.info("☁️ Google Cloud Firestore client initialized.")
            except Exception as e:
                logger.warning(f"☁️ Google Cloud Firestore client failed to initialize: {e}")
                self.firestore_client = None

    def enqueue_event(self, event: dict):
        event.setdefault("timestamp", datetime.utcnow().isoformat())
        if RABBIT_AVAILABLE:
            try:
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
                return
            except pika.exceptions.AMQPConnectionError as e:
                logger.warning(f"🐇 RabbitMQ connection failed ({e}), falling back to in-memory.")
        self._in_memory_queue.put(event)

    def start_background_loop(self):
        """Starts the main background worker thread."""
        if not self._loop_thread or not self._loop_thread.is_alive():
            self._stop_event.clear()
            target_loop = self._rabbit_consumer_loop if RABBIT_AVAILABLE else self._in_memory_consumer_loop
            self._loop_thread = threading.Thread(target=target_loop, daemon=True, name="CognitiveLoop")
            self._loop_thread.start()
            logger.info("🧠 Cognitive background loop started.")

    def stop_background_loop(self):
        if self._loop_thread and self._loop_thread.is_alive():
            logger.info("🧠 Sending stop signal to cognitive background loop...")
            self._stop_event.set()
            self._loop_thread.join(timeout=10)
            logger.info("🧠 Cognitive background loop stopped.")

    def is_running(self) -> bool:
        return self._loop_thread is not None and self._loop_thread.is_alive()

    def _persist_event(self, event: dict):
        with self.app.app_context():
            try:
                with get_session_scope() as session:
                    ev = EventLog(
                        event_type=event.get("type", "unknown"),
                        message=f"Event payload keys: {list(event.get('payload', {}).keys())}",
                        timestamp=datetime.fromisoformat(event.get("timestamp"))
                    )
                    session.add(ev)
            except Exception as e:
                logger.error(f"💾 SQL persist error: {e}", exc_info=True)

    def _in_memory_consumer_loop(self):
        while not self._stop_event.is_set():
            try:
                event = self._in_memory_queue.get(timeout=self.config["COGNITIVE_LOOP_DELAY"])
                self._persist_event(event)
                self._in_memory_queue.task_done()
            except Empty:
                continue

    def _rabbit_consumer_loop(self):
        while not self._stop_event.is_set():
            try:
                params = pika.URLParameters(self.config["COGNITIVE_RABBITMQ_URL"])
                connection = pika.BlockingConnection(params)
                channel = connection.channel()
                channel.queue_declare(queue=self.config["COGNITIVE_RABBIT_QUEUE"], durable=True)
                for method_frame, properties, body in channel.consume(self.config["COGNITIVE_RABBIT_QUEUE"]):
                    if self._stop_event.is_set():
                        break
                    try:
                        event = json.loads(body)
                        self._persist_event(event)
                        channel.basic_ack(method_frame.delivery_tag)
                    except Exception:
                        channel.basic_nack(method_frame.delivery_tag, requeue=True)
                        time.sleep(5)
                channel.cancel()
                connection.close()
            except pika.exceptions.AMQPConnectionError:
                self._stop_event.wait(10)

cognitive_bp = Blueprint('cognitive_bp', __name__)

@cognitive_bp.route('/cognitive/event', methods=['POST'])
def cognitive_event() -> tuple[Response, int]:
    from ..extensions import cognitive_system
    event = request.get_json()
    if not event or not isinstance(event, dict) or "type" not in event:
        return jsonify({"error": "Event must be a JSON object with a 'type' field."}), http.HTTPStatus.BAD_REQUEST
    cognitive_system.enqueue_event(event)
    return jsonify({"message": "Event accepted for processing."}), http.HTTPStatus.ACCEPTED

# Singleton instance of CognitiveSystem
cognitive_system = CognitiveSystem()
