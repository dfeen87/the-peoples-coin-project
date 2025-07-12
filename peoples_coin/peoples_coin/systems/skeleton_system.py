import os
import logging
import uuid
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, request, jsonify, abort, g, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from redis import Redis, RedisError
from pydantic import BaseModel, ValidationError, Field
from flasgger import Swagger, swag_from

# Import your validate_transaction function
from peoples_coin.validation.validate_transaction import validate_transaction

# ==== Logging Setup ====
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format='[%(asctime)s] %(levelname)s %(name)s %(message)s'
)
logger = logging.getLogger(__name__)

# ==== Input Models ====

class NodeRegistrationModel(BaseModel):
    node_id: str = Field(..., min_length=3, max_length=64, description="Unique Node ID")
    ip_address: str = Field(..., description="Node IP address")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")

class TransactionModel(BaseModel):
    key: str
    value: str
    contributor: str

# ==== API Key Auth Decorator ====

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if not api_key or api_key not in current_app.config["API_KEYS"]:
            logger.warning(f"Unauthorized access attempt from {request.remote_addr} with key: {api_key}")
            abort(401, description="Invalid or missing API key")
        g.api_key = api_key
        return f(*args, **kwargs)
    return decorated

# ==== Flask App Factory ====

def create_app():
    app = Flask(__name__)
    CORS(app)  # Enable CORS for all domains on all routes

    # Config
    app.config.update(
        API_KEYS=set(os.getenv("SKELETON_API_KEYS", "skeletonkey,defaultkey").split(",")),
        RATELIMIT_DEFAULT="50 per hour;10 per minute",
        DEBUG=os.getenv('SKELETON_DEBUG', 'false').lower() == 'true',
        SWAGGER={
            'title': "People's Coin Skeleton System API",
            'uiversion': 3,
        }
    )
    logger.info(f"Skeleton System: Debug mode = {app.config['DEBUG']}")

    # Redis-backed rate limiter with fallback
    redis_uri = f"redis://{os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', '6379')}/{os.getenv('REDIS_DB_SKELETON', '2')}"
    try:
        Redis.from_url(redis_uri, socket_connect_timeout=2).ping()
        limiter = Limiter(key_func=get_remote_address, storage_uri=redis_uri)
        logger.info("Skeleton System: Using Redis backend for rate limiting.")
    except (RedisError, Exception) as e:
        limiter = Limiter(key_func=get_remote_address)
        logger.warning(f"Skeleton System: Redis unavailable, falling back to in-memory rate limiting. Error: {e}")
    limiter.init_app(app)

    # Swagger docs setup
    Swagger(app)

    # ==== Correlation ID middleware ====
    @app.before_request
    def add_correlation_id():
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        g.correlation_id = correlation_id

    # ==== Routes ====

    @app.route("/", methods=["GET"])
    def index():
        return jsonify({"message": "Welcome to The People's Coin Skeleton System"}), 200

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify(status="Skeleton System operational", timestamp=datetime.now(timezone.utc).isoformat()), 200

    @app.route("/readiness", methods=["GET"])
    def readiness():
        # Could perform DB or dependency checks here
        return jsonify(status="ready"), 200

    @app.route("/register_node", methods=["POST"])
    @limiter.limit("10 per minute")
    @require_api_key
    @swag_from({
        'tags': ['Nodes'],
        'parameters': [{
            'name': 'body',
            'in': 'body',
            'schema': NodeRegistrationModel.schema(),
            'required': True,
            'description': 'Node registration payload'
        }],
        'responses': {
            201: {'description': 'Node registered successfully'},
            400: {'description': 'Validation error'},
            401: {'description': 'Unauthorized'},
            429: {'description': 'Rate limit exceeded'}
        }
    })
    def register_node():
        try:
            data = request.get_json()
            node = NodeRegistrationModel(**data)
            # TODO: Integrate real node registration logic here
            logger.info(f"Node registered: {node.node_id} by API key: {g.api_key}")
            return jsonify({"status": "ok", "node_id": node.node_id}), 201
        except ValidationError as e:
            logger.warning(f"Validation failed: {e.json()}")
            return jsonify({"error": "Validation error", "details": e.errors()}), 400
        except Exception as ex:
            logger.error(f"Unexpected error during node registration: {ex}", exc_info=True)
            return jsonify({"error": "Internal server error"}), 500

    @app.route("/nodes", methods=["GET"])
    @limiter.limit("20 per minute")
    @require_api_key
    @swag_from({
        'tags': ['Nodes'],
        'responses': {
            200: {'description': 'List of registered nodes'},
            401: {'description': 'Unauthorized'},
            429: {'description': 'Rate limit exceeded'}
        }
    })
    def list_nodes():
        # TODO: Replace stub with actual node retrieval
        nodes = [{"node_id": "node1_stub"}, {"node_id": "node2_stub"}]
        return jsonify(nodes), 200

    @app.route("/validate_transaction", methods=["POST"])
    @limiter.limit("10 per minute")
    @require_api_key
    @swag_from({
        'tags': ['Transactions'],
        'parameters': [{
            'name': 'body',
            'in': 'body',
            'schema': TransactionModel.schema(),
            'required': True,
            'description': 'Transaction data to validate'
        }],
        'responses': {
            200: {'description': 'Transaction is valid'},
            400: {'description': 'Validation failed'},
            401: {'description': 'Unauthorized'},
            429: {'description': 'Rate limit exceeded'}
        }
    })
    def validate_transaction_endpoint():
        try:
            data = request.get_json()
            if data is None:
                return jsonify({"error": "Missing JSON body"}), 400

            is_valid, result = validate_transaction(data)
            if not is_valid:
                return jsonify({"valid": False, "errors": result}), 400

            return jsonify({"valid": True, "data": result}), 200

        except Exception as ex:
            logger.error(f"Error validating transaction: {ex}", exc_info=True)
            return jsonify({"error": "Internal server error"}), 500

    # === Error Handlers ===
    @app.errorhandler(400)
    def bad_request(e):
        return jsonify(error=getattr(e, 'description', 'Bad request')), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify(error=getattr(e, 'description', 'Unauthorized')), 401

    @app.errorhandler(404)
    def not_found(e):
        return jsonify(error="Resource not found"), 404

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        return jsonify(error="Rate limit exceeded"), 429

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify(error="Internal server error"), 500

    # ==== Graceful shutdown hook (if needed) ====
    import signal

    def handle_shutdown_signal(signum, frame):
        logger.info(f"Received shutdown signal ({signum}). Cleaning up...")
        # Add cleanup code here (close DB connections, background threads, etc.)
        logger.info("Cleanup complete. Exiting.")
        exit(0)

    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    return app

if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("SKELETON_PORT", 5002))
    logger.info(f"Starting Skeleton System API on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, use_reloader=False)

