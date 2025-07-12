import os
import json
import logging
import threading
import time
from datetime import datetime
from queue import Queue, Empty
from contextlib import contextmanager

from flask import Blueprint, request, jsonify, current_app

from ..db import db
from ..db.models import CognitiveEvent

try:
    import pika
    RABBIT_AVAILABLE = True
except ImportError:
    RABBIT_AVAILABLE = False

try:
    from google.cloud import firestore
    GCP_AVAILABLE = True
except ImportError:
    GCP_AVAILABLE = False

logger = logging.getLogger("cognitive_system")
cognitive_bp = Blueprint('cognitive_bp', __name__)

# --- Configuration ---
_LOOP_DELAY = float(os.getenv("COGNITIVE_LOOP_DELAY", 5))
_REFLECTION_INTERVAL = float(os.getenv("COGNITIVE_REFLECTION_INTERVAL", 30))
_RABBITMQ_URL = os.getenv("COGNITIVE_RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
_RABBIT_QUEUE = os.getenv("COGNITIVE_RABBIT_QUEUE", "cognitive_events")
_FIRESTORE_COLLECTION = os.getenv("COGNITIVE_FIRESTORE_COLLECTION", "cognitive_memory")

# --- State ---
_thought_loop_running = False
_loop_thread = None
_loop_lock = threading.Lock()
_event_queue = Queue() if not RABBIT_AVAILABLE else None

# --- GCP Client Initialization ---
_firestore_client = None
if GCP_AVAILABLE:
    try:
        _firestore_client = firestore.Client()
        logger.info("☁️ Google Cloud Firestore client initialized.")
    except Exception as e:
        logger.warning(f"☁️ Google Cloud Firestore client failed to initialize: {e}")
        _firestore_client = None

# --- Database Session Context Manager ---
@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = db.session
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# --- Event Queueing ---
def enqueue_event(event: dict):
    if RABBIT_AVAILABLE:
        try:
            with pika.BlockingConnection(pika.URLParameters(_RABBITMQ_URL)) as conn:
                channel = conn.channel()
                channel.queue_declare(queue=_RABBIT_QUEUE, durable=True)
                channel.basic_publish(
                    exchange='',
                    routing_key=_RABBIT_QUEUE,
                    body=json.dumps(event),
                    properties=pika.BasicProperties(delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE)
                )
            logger.info(f"🐇 Event enqueued to RabbitMQ: {event.get('type')}")
            return
        except pika.exceptions.AMQPConnectionError as e:
            logger.warning(f"🐇 RabbitMQ connection failed ({e}), falling back to in-memory queue.")
    _event_queue.put(event)
    logger.info(f"🧠 Event enqueued (in-memory): {event.get('type')}")


# --- Core Logic & Background Thread ---
def _persist_event(event: dict):
    """Persist event to SQL DB and optionally Firestore."""
    try:
        with session_scope() as session:
            ev = CognitiveEvent(
                event_type=event.get("type", "unknown"),
                payload=json.dumps(event.get("payload", {})),
                timestamp=event.get("timestamp", datetime.utcnow().isoformat())
            )
            session.add(ev)
        logger.info(f"🧠 Event persisted in database: {ev.event_type}")
    except Exception as e:
        logger.error(f"Failed to persist event: {e}", exc_info=True)

    if _firestore_client:
        try:
            doc_ref = _firestore_client.collection(_FIRESTORE_COLLECTION).document()
            doc_ref.set(event)
            logger.debug(f"☁️ Event persisted to Firestore: {event.get('type')}")
        except Exception as e:
            logger.error(f"☁️ Firestore persist error: {e}")


def reflect():
    """Periodically log a summary of cognitive events."""
    try:
        with session_scope() as session:
            counts = session.query(
                CognitiveEvent.event_type,
                db.func.count(CognitiveEvent.id)
            ).group_by(CognitiveEvent.event_type).all()
            summary = {k: v for k, v in counts}
        logger.info(f"🧠 Reflection: {json.dumps(summary, indent=2)}")
    except Exception as e:
        logger.error(f"Failed to perform reflection: {e}", exc_info=True)


def _thought_loop():
    logger.info("🧠 Thought loop starting.")
    last_reflection = 0

    def process_event(event_data):
        logger.info(f"🧠 Processing event: {event_data.get('type')}")
        _persist_event(event_data)

    while _thought_loop_running:
        processed_event = False
        if RABBIT_AVAILABLE:
            try:
                with pika.BlockingConnection(pika.URLParameters(_RABBITMQ_URL)) as conn:
                    channel = conn.channel()
                    method_frame, _, body = channel.basic_get(queue=_RABBIT_QUEUE)
                    if method_frame:
                        process_event(json.loads(body))
                        channel.basic_ack(method_frame.delivery_tag)
                        processed_event = True
            except pika.exceptions.AMQPConnectionError as e:
                logger.error(f"🐇 Consumer connection failed: {e}")
                time.sleep(10)
        else:
            try:
                event = _event_queue.get(block=False)
                process_event(event)
                processed_event = True
            except Empty:
                pass

        now = time.time()
        if now - last_reflection >= _REFLECTION_INTERVAL:
            reflect()
            last_reflection = now

        if not processed_event:
            time.sleep(_LOOP_DELAY)

    logger.info("🧠 Thought loop stopped.")


# --- Public API & Flask Routes ---
def start_thought_loop():
    global _thought_loop_running, _loop_thread
    with _loop_lock:
        if not _thought_loop_running:
            _thought_loop_running = True
            _loop_thread = threading.Thread(target=_thought_loop, daemon=True, name="CognitiveLoop")
            _loop_thread.start()
            logger.info("🧠 Thought loop start signal sent.")


def stop_thought_loop():
    global _thought_loop_running
    if _thought_loop_running:
        _thought_loop_running = False
        if _loop_thread:
            _loop_thread.join(timeout=10)
        logger.info("🧠 Thought loop stop signal sent.")


@cognitive_bp.route('/cognitive/status', methods=['GET'])
def cognitive_status():
    pending_events = "N/A"
    if _event_queue:
        pending_events = _event_queue.qsize()
    return jsonify({
        "status": "running" if _thought_loop_running else "stopped",
        "event_queue": "RabbitMQ" if RABBIT_AVAILABLE else "In-Memory",
        "pending_events": pending_events,
    })


@cognitive_bp.route('/cognitive/event', methods=['POST'])
def cognitive_event():
    event = request.get_json()
    if not event or not isinstance(event, dict) or "type" not in event:
        return jsonify({"error": "Event must be a JSON object with a 'type' field."}), 400

    event.setdefault("timestamp", datetime.utcnow().isoformat())
    event.setdefault("payload", {})

    enqueue_event(event)
    return jsonify({"message": "Event accepted."}), 202


# --- App Integration ---
def register_cognitive_system(app):
    """Registers the blueprint."""
    app.register_blueprint(cognitive_bp)
    logger.info("🧠 Cognitive system blueprint registered.")

    # The start_thought_loop() call is now handled by run.py

