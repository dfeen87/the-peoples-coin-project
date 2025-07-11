import os
import logging
from datetime import datetime, timezone
from flask import Flask, Blueprint, request, jsonify, current_app, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from redis import Redis, RedisError
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from functools import wraps
import atexit
import json
import traceback

# --- Setup logging for this module ---
logger = logging.getLogger(__name__)

# --- Import shared DB and Models (from the main package's db sub-package) ---
from ..db import db
from ..db.models import DataEntry, EventLog

# --- Import other components if needed (e.g., validation) ---
from ..validation import validate_transaction

# --- AILEE Controller (imported as needed by main app) ---
from .endocrine_system import AILEEController
ailee_controller = None # Global for this specific microservice instance

# REMOVED THE FOLLOWING LINE TO FIX CIRCULAR IMPORT:
# from peoples_coin.peoples_coin.systems.nervous_system import create_nervous_app


# ===== Factory Function to Create Flask App Instance =====
def create_nervous_app():
    """
    Factory function to create and configure the Nervous System Flask application.
    This prevents the app from being instantiated on module import.
    """
    app = Flask(__name__)

    # --- Configuration for this specific microservice ---
    instance_path = os.path.abspath(os.path.expanduser("instance"))
    os.makedirs(instance_path, exist_ok=True)
    sqlite_db_path = os.path.join(instance_path, "nervous_system.db")
    sqlite_db_uri = f"sqlite:///{sqlite_db_path}"

    app.config.update(
        SQLALCHEMY_DATABASE_URI=os.getenv('NERVOUS_DATABASE_URL', sqlite_db_uri),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        DEBUG=os.getenv('NERVOUS_DEBUG', 'true').lower() == 'true',
        API_KEYS=set(os.getenv('NERVOUS_API_KEYS', 'nervouskey,defaultkey').split(',')),
        RATELIMIT_DEFAULT="50 per hour;10 per minute",
    )

    logger.info(f"Nervous System using DB URI: {app.config['SQLALCHEMY_DATABASE_URI']}")

    # --- Initialize DB for THIS microservice ---
    db.init_app(app)

    # --- Rate limiter for THIS microservice ---
    try:
        redis_conn = Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=int(os.getenv('REDIS_DB_NERVOUS', 1)),
            decode_responses=True,
            socket_connect_timeout=2
        )
        redis_conn.ping()
        limiter = Limiter(
            key_func=get_remote_address,
            storage_uri=f"redis://{redis_conn.connection_pool.connection_kwargs['host']}:{redis_conn.connection_pool.connection_kwargs['port']}/{redis_conn.connection_pool.connection_kwargs['db']}"
        )
        app.logger.info("Nervous System using Redis backend for rate limiting.")
    except (RedisError, Exception) as e:
        limiter = Limiter(key_func=get_remote_address)
        app.logger.warning(f"Nervous System Redis not available, falling back to in-memory rate limiting. Error: {e}")
    limiter.init_app(app)

    # --- Thread safety & thread pool executor (local to this microservice) ---
    app.data_lock = Lock()
    app.event_lock = Lock()
    app.ailee_lock = Lock()
    app.executor = ThreadPoolExecutor(max_workers=2)

    # ===== API Key Auth Decorator (local to this microservice) =====
    def require_api_key(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            api_key = request.headers.get('X-API-Key')
            if not api_key:
                current_app.logger.warning("Nervous System: Missing API key on request.")
                return jsonify({"error": "Unauthorized: Missing API Key"}), 401
            if api_key not in current_app.config['API_KEYS']:
                current_app.logger.warning(f"Nervous System: Invalid API key attempted: {api_key}")
                return jsonify({"error": "Unauthorized: Invalid API Key"}), 401
            g.api_key = api_key
            return f(*args, **kwargs)
        return decorated

    # ===== Logging Events (local to this microservice) =====
    def log_event(event_type: str, message: str):
        timestamp = datetime.now(timezone.utc).isoformat()
        with app.app_context():
            event = EventLog(event_type=event_type, message=message, timestamp=timestamp, source_module=__name__)
            try:
                with app.event_lock:
                    db.session.add(event)
                    db.session.commit()
                current_app.logger.info(f"[{timestamp}] {event_type}: {message}")
            except Exception as e:
                current_app.logger.error(f"Nervous System Failed to log event {event_type}: {e}\n{traceback.format_exc()}")
                db.session.rollback()

    # ===== Request Logging Decorator (local to this microservice) =====
    def log_request(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            current_app.logger.debug(f"Nervous System Request start: {request.method} {request.path} from {request.remote_addr}")
            try:
                response = f(*args, **kwargs)
                current_app.logger.debug(f"Nervous System Request success: {request.method} {request.path} Status: {response.status_code}")
                return response
            except Exception as e:
                current_app.logger.error(f"Nervous System Request error: {request.method} {request.path} - {e}\n{traceback.format_exc()}")
                raise
        return decorated

    # ===== Graceful Shutdown Handler (local to this microservice) =====
    def graceful_shutdown():
        logger.info("Nervous System server shutting down gracefully.")
        try:
            db.session.remove()
        except Exception:
            logger.warning("Nervous System: Error removing DB session on shutdown.")
        global ailee_controller
        if ailee_controller and ailee_controller.is_running():
            logger.info("Stopping AILEEController (Nervous System's instance) on shutdown.")
            with app.ailee_lock:
                ailee_controller.stop()
        app.executor.shutdown(wait=True)

    atexit.register(graceful_shutdown)

    # ===== Routes for Nervous System Microservice =====
    @app.route("/nervous/status", methods=["GET"])
    @log_request
    def nervous_status():
        """Health check for the Nervous System microservice."""
        status = "running" if (ailee_controller and ailee_controller.is_running()) else "stopped"
        return jsonify({"status": "Nervous System operational", "ailee_status": status, "timestamp": datetime.now(timezone.utc).isoformat()}), 200

    @app.route("/nervous/process_data", methods=["POST"])
    @require_api_key
    @limiter.limit("5 per minute")
    @log_request
    def process_data():
        """Example endpoint for Nervous System to process data."""
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 415
        data = request.get_json()
        logger.info(f"Nervous System received data for processing: {data}")

        try:
            is_valid, result = validate_transaction(data)
            if not is_valid:
                return jsonify({"error": "Validation failed", "details": result}), 400

            contribution = result
            new_entry = DataEntry(
                value=json.dumps({"key": contribution.key, "value": contribution.value, "contributor": contribution.contributor, "tags": contribution.tags}),
                data_type='nervous_input', # Add this if your DataEntry model has 'data_type'
                source='nervous_system' # Add this if your DataEntry model has 'source'
            )
            with app.data_lock:
                db.session.add(new_entry)
                db.session.commit()
            log_event('data_processed_nervous', f"Nervous System processed and stored data: {contribution.key}")
            return jsonify({"message": "Data received and processed by Nervous System", "key": contribution.key}), 200
        except Exception as e:
            logger.error(f"Nervous System failed to store processed data: {e}\n{traceback.format_exc()}")
            db.session.rollback()
            return jsonify({"error": f"Nervous System processing failed: {e}"}), 500

    @app.route("/nervous/ailee/start", methods=["POST"])
    @require_api_key
    @log_request
    def nervous_ailee_start():
        global ailee_controller
        with app.ailee_lock:
            if ailee_controller and ailee_controller.is_running():
                return jsonify({"message": "AILEE already running"}), 400
            try:
                # When Nervous System starts AILEE, it needs to pass its own app and db
                # This ensures AILEE's context is tied to the Nervous System's app instance
                ailee_controller = AILEEController.get_instance(app, db) # Use get_instance here
                ailee_controller.start()
                current_app.logger.info("Nervous System AILEE started successfully.")
                return jsonify({"message": "Nervous System AILEE started"}), 200
            except Exception as e:
                current_app.logger.error(f"Nervous System Failed to start AILEE: {e}\n{traceback.format_exc()}")
                return jsonify({"error": f"Nervous System Failed to start AILEE: {e}"}), 500

    @app.route("/nervous/ailee/stop", methods=["POST"])
    @require_api_key
    @log_request
    def nervous_ailee_stop():
        global ailee_controller
        with app.ailee_lock:
            if not ailee_controller or not ailee_controller.is_running():
                return jsonify({"message": "AILEE not running"}), 400
            try:
                ailee_controller.stop()
                ailee_controller = None # Clear the reference after stopping
                current_app.logger.info("Nervous System AILEE stopped successfully.")
                return jsonify({"message": "Nervous System AILEE stopped"}), 200
            except Exception as e:
                current_app.logger.error(f"Nervous System Failed to stop AILEE: {e}\n{traceback.format_exc()}")
                return jsonify({"error": f"Nervous System Failed to stop AILEE: {e}"}), 500

    # ===== Error Handlers (local to this microservice) =====
    @app.errorhandler(404)
    def not_found(err):
        current_app.logger.warning(f"Nervous System 404 Not Found: {request.path}")
        return jsonify({"error": "Nervous System: Endpoint not found"}), 404

    @app.errorhandler(429)
    def ratelimit_handler(err):
        current_app.logger.warning(f"Nervous System Rate limit exceeded for {request.remote_addr} at {request.path}")
        return jsonify({"error": "Nervous System: Rate limit exceeded. Please slow down."}), 429

    @app.errorhandler(500)
    def internal_error(err):
        current_app.logger.error(f"Nervous System Internal server error: {err}\n{traceback.format_exc()}")
        return jsonify({"error": "Nervous System: Internal server error"}), 500

    # ===== Database Initialization for this Microservice (run once per app creation) =====
    with app.app_context():
        db.create_all()
        logger.info("Nervous System database initialized and tables created.")

    return app # Return the configured Flask app instance

# This block ensures the app runs when this file is executed directly
if __name__ == '__main__':
    nervous_app = create_nervous_app()
    logging.basicConfig(level=logging.DEBUG if nervous_app.config['DEBUG'] else logging.INFO)
    logger.info("Starting Nervous System microservice...")
    nervous_app.run(host="0.0.0.0", port=int(os.getenv('NERVOUS_PORT', 5001)), debug=nervous_app.config['DEBUG'], use_reloader=False)

