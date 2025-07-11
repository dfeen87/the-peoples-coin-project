import os
import json
import logging
import threading
import time
import sqlite3
from datetime import datetime
from collections import defaultdict
from queue import Queue, Empty

from flask import Blueprint, request, jsonify, Response, current_app
from dataclasses import dataclass, asdict

try:
    import pika
    RABBIT_AVAILABLE = True
except ImportError:
    RABBIT_AVAILABLE = False

try:
    from google.cloud import firestore
    from google.cloud import pubsub_v1
    from google.cloud import storage
    GCP_AVAILABLE = True
except ImportError:
    GCP_AVAILABLE = False


logger = logging.getLogger("cognitive_system")
logger.setLevel(logging.INFO)  # Can be overridden by your app logging config

cognitive_bp = Blueprint('cognitive_bp', __name__)

# ===== Config =====

_LOOP_DELAY = float(os.getenv("COGNITIVE_LOOP_DELAY", 5))  # seconds
_REFLECTION_INTERVAL = float(os.getenv("COGNITIVE_REFLECTION_INTERVAL", 30))  # seconds
_SNAPSHOT_INTERVAL = float(os.getenv("COGNITIVE_SNAPSHOT_INTERVAL", 300))  # seconds (5 min)
_DB_PATH = os.getenv("COGNITIVE_DB_PATH", "instance/cognitive_memory.db")
_RABBITMQ_URL = os.getenv("COGNITIVE_RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
_RABBIT_QUEUE = os.getenv("COGNITIVE_RABBIT_QUEUE", "cognitive_events")
_FIRESTORE_COLLECTION = os.getenv("COGNITIVE_FIRESTORE_COLLECTION", "cognitive_memory")
_PUBSUB_TOPIC = os.getenv("COGNITIVE_PUBSUB_TOPIC", "cognitive_events")
_GCS_BUCKET = os.getenv("COGNITIVE_GCS_BUCKET", None)  # optional for snapshot uploads

# ===== State =====

_memory_store = defaultdict(list)  # key -> list of {value, timestamp}
_thought_loop_running = False
_loop_thread = None
_loop_lock = threading.Lock()
_last_reflection = 0
_last_snapshot = 0

# Event queue setup
if RABBIT_AVAILABLE:
    try:
        _rabbit_conn = pika.BlockingConnection(pika.URLParameters(_RABBITMQ_URL))
        _rabbit_channel = _rabbit_conn.channel()
        _rabbit_channel.queue_declare(queue=_RABBIT_QUEUE, durable=True)

        def enqueue_event(event):
            _rabbit_channel.basic_publish(
                exchange='',
                routing_key=_RABBIT_QUEUE,
                body=json.dumps(event),
                properties=pika.BasicProperties(delivery_mode=2)  # persistent message
            )
            logger.info(f"🧠 Event enqueued to RabbitMQ: {event}")

        logger.info("🐇 RabbitMQ connected and ready for events.")

    except Exception as e:
        logger.warning(f"🐇 RabbitMQ unavailable: {e}, falling back to in-memory queue.")
        RABBIT_AVAILABLE = False

if not RABBIT_AVAILABLE:
    _event_queue = Queue()

    def enqueue_event(event):
        _event_queue.put(event)
        logger.info(f"🧠 Event enqueued (in-memory): {event}")

# GCP Clients (optional)
_firestore_client = None
_pubsub_publisher = None
_storage_client = None
if GCP_AVAILABLE:
    try:
        _firestore_client = firestore.Client()
        _pubsub_publisher = pubsub_v1.PublisherClient()
        _storage_client = storage.Client()
        logger.info("☁️ Google Cloud clients initialized.")
    except Exception as e:
        logger.warning(f"☁️ Google Cloud clients failed to initialize: {e}")
        _firestore_client = None
        _pubsub_publisher = None
        _storage_client = None


# ===== Persistence =====

def _init_db():
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT,
            value TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()
    logger.info(f"🧠 SQLite DB initialized at {_DB_PATH}")

def _persist_memory(key, value):
    try:
        conn = sqlite3.connect(_DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO memory (key, value, timestamp) VALUES (?, ?, ?)",
            (key, json.dumps(value), datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to persist memory key={key}: {e}")

def _load_memory():
    try:
        conn = sqlite3.connect(_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT key, value, timestamp FROM memory")
        rows = c.fetchall()
        conn.close()
        for key, val, ts in rows:
            _memory_store[key].append({"value": json.loads(val), "timestamp": ts})
        logger.info(f"🧠 Loaded {sum(len(v) for v in _memory_store.values())} memories from persistence.")
    except Exception as e:
        logger.error(f"Failed to load memory from DB: {e}")

def _upload_snapshot_to_gcs(snapshot_path):
    if not _storage_client or not _GCS_BUCKET:
        logger.info("☁️ GCS upload skipped (no bucket or client).")
        return
    try:
        bucket = _storage_client.bucket(_GCS_BUCKET)
        blob_name = os.path.basename(snapshot_path)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(snapshot_path)
        logger.info(f"☁️ Snapshot uploaded to GCS bucket '{_GCS_BUCKET}' as '{blob_name}'.")
    except Exception as e:
        logger.error(f"Failed to upload snapshot to GCS: {e}")

def _snapshot_to_local_and_cloud():
    snapshot = {
        "timestamp": datetime.utcnow().isoformat(),
        "memory": {k: v for k, v in _memory_store.items()}
    }
    os.makedirs("instance", exist_ok=True)
    snapshot_path = f"instance/memory_snapshot_{int(time.time())}.json"
    try:
        with open(snapshot_path, "w") as f:
            json.dump(snapshot, f, indent=2)
        logger.info(f"🧠 Snapshot saved locally at {snapshot_path}")
        _upload_snapshot_to_gcs(snapshot_path)
    except Exception as e:
        logger.error(f"Failed to save snapshot: {e}")

# ===== Data structures =====

@dataclass
class CognitiveEvent:
    type: str
    payload: dict
    timestamp: str = datetime.utcnow().isoformat()

# ===== Internal Methods =====

def _log_memory(key, value):
    record = {
        "value": value,
        "timestamp": datetime.utcnow().isoformat()
    }
    _memory_store[key].append(record)
    _persist_memory(key, value)

    # Optional: Persist to Firestore if available
    if _firestore_client:
        try:
            doc_ref = _firestore_client.collection(_FIRESTORE_COLLECTION).document()
            doc_ref.set({
                "key": key,
                "value": value,
                "timestamp": datetime.utcnow()
            })
            logger.debug(f"☁️ Memory persisted to Firestore key={key}")
        except Exception as e:
            logger.error(f"☁️ Firestore persist error: {e}")

def _process_event(event):
    logger.info(f"🧠 Processing event: {event}")
    event_type = event.get("type", "unknown")
    if event_type == "anomaly":
        logger.warning(f"🚨 Anomaly detected: {event}")
    _log_memory(event_type, event)

def reflect():
    # Simple reflection: log counts and keys
    summary = {
        "timestamp": datetime.utcnow().isoformat(),
        "summary": {k: len(v) for k, v in _memory_store.items()}
    }
    logger.info(f"🧠 Reflection: {json.dumps(summary, indent=2)}")

# RabbitMQ consumer helper
def _consume_rabbit():
    if not RABBIT_AVAILABLE:
        return False
    for method_frame, properties, body in _rabbit_channel.consume(_RABBIT_QUEUE, inactivity_timeout=1):
        if not _thought_loop_running:
            break
        if body:
            try:
                event = json.loads(body)
                _process_event(event)
                _rabbit_channel.basic_ack(method_frame.delivery_tag)
                return True
            except Exception as e:
                logger.error(f"Failed to process RabbitMQ event: {e}")
    return False

# Thought loop function
def _thought_loop():
    global _thought_loop_running, _last_reflection, _last_snapshot
    logger.info("🧠 Thought loop started.")
    while _thought_loop_running:
        processed = False
        if RABBIT_AVAILABLE:
            processed = _consume_rabbit()
        else:
            try:
                event = _event_queue.get(timeout=_LOOP_DELAY)
                _process_event(event)
                processed = True
            except Empty:
                pass

        now = time.time()
        if now - _last_reflection >= _REFLECTION_INTERVAL:
            reflect()
            _last_reflection = now

        if now - _last_snapshot >= _SNAPSHOT_INTERVAL:
            _snapshot_to_local_and_cloud()
            _last_snapshot = now

        if not processed:
            time.sleep(_LOOP_DELAY)

    logger.info("🧠 Thought loop stopped.")

# ===== Public API =====

def start_thought_loop():
    global _thought_loop_running, _loop_thread
    with _loop_lock:
        if not _thought_loop_running:
            _init_db()
            _load_memory()
            _thought_loop_running = True
            _loop_thread = threading.Thread(target=_thought_loop, daemon=True)
            _loop_thread.start()
            logger.info("🧠 Thought loop started.")
        else:
            logger.info("🧠 Thought loop already running.")

def stop_thought_loop():
    global _thought_loop_running, _loop_thread
    with _loop_lock:
        if _thought_loop_running:
            _thought_loop_running = False
            logger.info("🧠 Stopping thought loop…")
            if _loop_thread:
                _loop_thread.join()
                logger.info("🧠 Thought loop thread joined.")

# ===== ML Anomaly Detection Stub =====

def detect_anomaly(data):
    # Placeholder for real ML inference
    logger.info("🧠 Running anomaly detection (stub).")
    return {
        "is_anomaly": False,
        "score": 0.05,
        "details": "No significant anomaly detected."
    }

# ===== Metrics =====

def generate_metrics():
    metrics = [
        '# HELP cognitive_memory_entries_total Total memory entries stored',
        '# TYPE cognitive_memory_entries_total counter',
        f'cognitive_memory_entries_total {sum(len(v) for v in _memory_store.values())}',

        '# HELP cognitive_pending_events Number of pending events',
        '# TYPE cognitive_pending_events gauge',
        f'cognitive_pending_events {_event_queue.qsize() if not RABBIT_AVAILABLE else "N/A"}',

        '# HELP cognitive_loop_status Thought loop running status',
        '# TYPE cognitive_loop_status gauge',
        f'cognitive_loop_status {1 if _thought_loop_running else 0}',
    ]
    return "\n".join(metrics) + "\n"

# ===== Flask Routes =====

@cognitive_bp.route('/cognitive/status', methods=['GET'])
def cognitive_status():
    status = "running" if _thought_loop_running else "stopped"
    return jsonify({
        "status": status,
        "memory_size": sum(len(v) for v in _memory_store.values()),
        "pending_events": _event_queue.qsize() if not RABBIT_AVAILABLE else "N/A",
        "timestamp": datetime.utcnow().isoformat()
    })

@cognitive_bp.route('/cognitive/memory', methods=['GET'])
def cognitive_memory():
    return jsonify({k: v for k, v in _memory_store.items()})

@cognitive_bp.route('/cognitive/analyze', methods=['POST'])
def cognitive_analyze():
    data = request.get_json()
    logger.info(f"🧠 Analysis requested: {data}")
    result = detect_anomaly(data)
    return jsonify(result)

@cognitive_bp.route('/cognitive/event', methods=['POST'])
def cognitive_event():
    event = request.get_json()
    if not event or "type" not in event:
        return jsonify({"error": "Event must include a 'type' field."}), 400
    enqueue_event(event)
    return jsonify({"message": "Event accepted."}), 202

@cognitive_bp.route('/cognitive/reflect', methods=['POST'])
def cognitive_reflect():
    reflect()
    return jsonify({"message": "Reflection completed."})

@cognitive_bp.route('/metrics', methods=['GET'])
def metrics():
    return Response(generate_metrics(), mimetype='text/plain')

# ===== Integration =====

def register_cognitive_system(app):
    app.register_blueprint(cognitive_bp)
    logger.info("🧠 Cognitive system blueprint registered.")
    start_thought_loop()

# Optional graceful shutdown helper for your app:
def graceful_shutdown():
    logger.info("🧠 Graceful shutdown initiated.")
    stop_thought_loop()

import atexit
atexit.register(graceful_shutdown)

