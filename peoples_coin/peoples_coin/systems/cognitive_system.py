import os
import json
import logging
import threading
import time
import sqlite3
from datetime import datetime
from queue import Queue, Empty

from flask import Blueprint, request, jsonify, Response, current_app, g

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
_DB_PATH = os.getenv("COGNITIVE_DB_PATH", "instance/cognitive_memory.db")
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

# --- Database Management ---
def _init_db():
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    with sqlite3.connect(_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cognitive_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_type ON cognitive_events (event_type)')
        conn.commit()
    logger.info(f"🧠 SQLite DB initialized at {_DB_PATH}")

def get_db_conn():
    if 'cognitive_db' not in g:
        g.cognitive_db = sqlite3.connect(_DB_PATH, timeout=10)
    return g.cognitive_db

def close_db_conn(exception=None):
    db = g.pop('cognitive_db', None)
    if db is not None:
        db.close()

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
def _persist_event(conn: sqlite3.Connection, event: dict):
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO cognitive_events (event_type, payload, timestamp) VALUES (?, ?, ?)",
            (
                event.get("type", "unknown"),
                json.dumps(event.get("payload", {})),
                event.get("timestamp", datetime.utcnow().isoformat())
            )
        )
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Failed to persist event to SQLite: {e}")
        conn.rollback()

    if _firestore_client:
        try:
            doc_ref = _firestore_client.collection(_FIRESTORE_COLLECTION).document()
            doc_ref.set(event)
        except Exception as e:
            logger.error(f"☁️ Firestore persist error: {e}")

def reflect(conn: sqlite3.Connection):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT event_type, COUNT(*) FROM cognitive_events GROUP BY event_type")
        summary = dict(cursor.fetchall())
        logger.info(f"🧠 Reflection: {json.dumps(summary, indent=2)}")
    except sqlite3.Error as e:
        logger.error(f"Failed to perform reflection: {e}")

def _thought_loop():
    logger.info("🧠 Thought loop starting.")
    db_conn = sqlite3.connect(_DB_PATH, timeout=10)
    last_reflection = 0

    def process_event(event_data):
        logger.info(f"🧠 Processing event: {event_data.get('type')}")
        _persist_event(db_conn, event_data)

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
            reflect(db_conn)
            last_reflection = now

        if not processed_event:
            time.sleep(_LOOP_DELAY)

    db_conn.close()
    logger.info("🧠 Thought loop stopped.")


# --- Public API & Flask Routes ---
def start_thought_loop():
    global _thought_loop_running, _loop_thread
    with _loop_lock:
        if not _thought_loop_running:
            _init_db()
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
    """Registers the blueprint and the app context teardown function."""
    app.register_blueprint(cognitive_bp)
    logger.info("🧠 Cognitive system blueprint registered.")

    app.teardown_appcontext(close_db_conn)
    logger.info("🧠 Cognitive system DB teardown registered with the app.")
    
    # The start_thought_loop() call is now handled by run.py
