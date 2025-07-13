import os
import logging
import uuid
import http
import secrets
from datetime import datetime, timezone
from functools import wraps
import signal

from flask import Flask, request, jsonify, abort, g, current_app, Blueprint, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from redis import Redis, RedisError
from pydantic import BaseModel, ValidationError, Field
from flasgger import Swagger, swag_from

# ==============================================================================
# 1. Centralized Configuration
# ==============================================================================
class Config:
    """Centralized configuration class for the Flask app."""
    # Security
    SECRET_KEY = os.getenv("SECRET_KEY", "a-very-secret-key")
    API_KEYS = set(os.getenv("SKELETON_API_KEYS", "skeletonkey,defaultkey").split(","))

    # Environment
    DEBUG = os.getenv('SKELETON_DEBUG', 'false').lower() == 'true'
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    # Rate Limiting & Redis
    RATELIMIT_DEFAULT = "50 per hour;10 per minute"
    REDIS_URI = f"redis://{os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', '6379')}/{os.getenv('REDIS_DB_SKELETON', '2')}"

    # API Documentation
    SWAGGER = {
        'title': "People's Coin Skeleton System API",
        'uiversion': 3,
        'description': "API for the core skeleton system of The People's Coin.",
        'termsOfService': None,
        'contact': {
            'name': 'API Support',
            'url': 'http://example.com',
            'email': 'support@example.com',
        },
        'license': {
            'name': 'MIT',
            'url': 'https://opensource.org/licenses/MIT',
        },
    }


# ==============================================================================
# 2. Logging Setup
# ==============================================================================
logging.basicConfig(
    level=Config.LOG_LEVEL,
    format='[%(asctime)s] %(levelname)s %(name)s %(message)s'
)
logger = logging.getLogger(__name__)


# ==============================================================================
# 3. Pydantic Input Models
# ==============================================================================
class NodeRegistrationModel(BaseModel):
    node_id: str = Field(..., min_length=3, max_length=64, description="Unique Node ID")
    ip_address: str = Field(..., description="Node IP address")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


class TransactionModel(BaseModel):
    key: str
    value: str
    contributor: str


# ==============================================================================
# 4. Reusable Decorators
# ==============================================================================
def require_api_key(f):
    """Decorator to protect routes with API key authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            abort(http.HTTPStatus.UNAUTHORIZED, description="Missing API key")

        # Constant-time comparison for security
        is_valid = any(secrets.compare_digest(api_key, key) for key in current_app.config["API_KEYS"])

        if not is_valid:
            logger.warning(f"Unauthorized access attempt from {request.remote_addr}")
            abort(http.HTTPStatus.UNAUTHORIZED, description="Invalid API key")

        g.api_key = api_key
        return f(*args, **kwargs)
    return decorated


def validate_with(model: BaseModel):
    """Decorator to validate request JSON against a Pydantic model."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                data = request.get_json()
                if data is None:
                    raise ValueError("Request body must be JSON.")
                g.validated_data = model(**data)
            except ValidationError as e:
                logger.warning(f"Validation failed for {model.__name__}: {e.errors()}")
                return jsonify({"error": "Validation error", "details": e.errors()}), http.HTTPStatus.BAD_REQUEST
            except (ValueError, TypeError) as e:
                logger.warning(f"Malformed JSON received: {e}")
                return jsonify({"error": "Missing or malformed JSON"}), http.HTTPStatus.BAD_REQUEST
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ==============================================================================
# 5. Application Blueprint
# ==============================================================================
api_bp = Blueprint('api', __name__)

@api_bp.route("/", methods=["GET"])
def index() -> tuple[Response, int]:
    return jsonify({"message": "Welcome to The People's Coin Skeleton System"}), http.HTTPStatus.OK


@api_bp.route("/health", methods=["GET"])
def health() -> tuple[Response, int]:
    return jsonify(status="Skeleton System operational", timestamp=datetime.now(timezone.utc).isoformat()), http.HTTPStatus.OK


@api_bp.route("/readiness", methods=["GET"])
def readiness() -> tuple[Response, int]:
    # In a real app, check DB connection, Redis, etc.
    return jsonify(status="ready"), http.HTTPStatus.OK


@api_bp.route("/register_node", methods=["POST"])
@require_api_key
@validate_with(NodeRegistrationModel)
@swag_from({
    'tags': ['Nodes'],
    'parameters': [{'name': 'body', 'in': 'body', 'schema': NodeRegistrationModel.schema(), 'required': True}],
    'responses': {
        http.HTTPStatus.CREATED: {'description': 'Node registered successfully'},
        http.HTTPStatus.BAD_REQUEST: {'description': 'Validation error'},
        http.HTTPStatus.UNAUTHORIZED: {'description': 'Unauthorized'},
        http.HTTPStatus.TOO_MANY_REQUESTS: {'description': 'Rate limit exceeded'}
    }
})
def register_node() -> tuple[Response, int]:
    node: NodeRegistrationModel = g.validated_data
    # TODO: Integrate real node registration logic here
    logger.info(f"Node registered: {node.node_id} by API key ending in '...{g.api_key[-4:]}'")
    return jsonify({"status": "ok", "node_id": node.node_id}), http.HTTPStatus.CREATED


@api_bp.route("/nodes", methods=["GET"])
@require_api_key
@swag_from({
    'tags': ['Nodes'],
    'responses': {
        http.HTTPStatus.OK: {'description': 'List of registered nodes'},
        http.HTTPStatus.UNAUTHORIZED: {'description': 'Unauthorized'}
    }
})
def list_nodes() -> tuple[Response, int]:
    # TODO: Replace stub with actual node retrieval from a database
    nodes = [{"node_id": "node1_stub", "ip": "192.168.1.1"}, {"node_id": "node2_stub", "ip": "192.168.1.2"}]
    return jsonify(nodes), http.HTTPStatus.OK


@api_bp.route("/validate_transaction", methods=["POST"])
@require_api_key
@validate_with(TransactionModel)
@swag_from({
    'tags': ['Transactions'],
    'parameters': [{'name': 'body', 'in': 'body', 'schema': TransactionModel.schema(), 'required': True}],
    'responses': {
        http.HTTPStatus.OK: {'description': 'Transaction is valid'},
        http.HTTPStatus.BAD_REQUEST: {'description': 'Validation failed'},
        http.HTTPStatus.UNAUTHORIZED: {'description': 'Unauthorized'}
    }
})
def validate_transaction_endpoint() -> tuple[Response, int]:
    # In a real implementation, import from your project validation module
    # from peoples_coin.validation import validate_transaction

    # Mock implementation for demonstration:
    def mock_validate_transaction(data):
        return True, {"message": "Transaction appears valid."}

    is_valid, result = mock_validate_transaction(g.validated_data.dict())
    if not is_valid:
        return jsonify({"valid": False, "errors": result}), http.HTTPStatus.BAD_REQUEST
    return jsonify({"valid": True, "data": result}), http.HTTPStatus.OK


# ==============================================================================
# 6. Flask App Factory
# ==============================================================================
def create_app(config_object=Config) -> Flask:
    """Creates and configures a Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Initialize extensions
    CORS(app)
    Swagger(app, config=app.config['SWAGGER'])

    # Initialize rate limiter with Redis fallback
    try:
        Redis.from_url(app.config['REDIS_URI'], socket_connect_timeout=2).ping()
        limiter = Limiter(key_func=get_remote_address, storage_uri=app.config['REDIS_URI'])
        logger.info("Skeleton System: Using Redis backend for rate limiting.")
    except (RedisError, Exception) as e:
        limiter = Limiter(key_func=get_remote_address)  # In-memory fallback
        logger.warning(f"Skeleton System: Redis unavailable, falling back to in-memory rate limiting. Error: {e}")
    limiter.init_app(app)

    # Register middleware
    @app.before_request
    def add_correlation_id():
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        g.correlation_id = correlation_id

    # Register Blueprints
    app.register_blueprint(api_bp, url_prefix='/api/v1')

    # Register custom error handlers
    def create_error_handler(status_code, default_message):
        def handler(e):
            description = getattr(e, 'description', default_message)
            return jsonify(error=description), status_code
        return handler

    app.register_error_handler(http.HTTPStatus.BAD_REQUEST, create_error_handler(400, "Bad request"))
    app.register_error_handler(http.HTTPStatus.UNAUTHORIZED, create_error_handler(401, "Unauthorized"))
    app.register_error_handler(http.HTTPStatus.NOT_FOUND, create_error_handler(404, "Resource not found"))
    app.register_error_handler(http.HTTPStatus.TOO_MANY_REQUESTS, create_error_handler(429, "Rate limit exceeded"))
    app.register_error_handler(http.HTTPStatus.INTERNAL_SERVER_ERROR, create_error_handler(500, "Internal server error"))

    # Register graceful shutdown
    def handle_shutdown_signal(signum, frame):
        logger.info(f"Received shutdown signal ({signum}). Cleaning up...")
        # Add cleanup code here (e.g., close database connections)
        logger.info("Cleanup complete. Exiting.")
        exit(0)

    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    return app


# ==============================================================================
# 7. Main Execution Block
# ==============================================================================
if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("SKELETON_PORT", 5002))
    # Use reloader only if DEBUG is explicitly True
    use_reloader = app.config['DEBUG']
    logger.info(f"Starting Skeleton System API on http://0.0.0.0:{port} (Debug: {app.config['DEBUG']})")
    app.run(host="0.0.0.0", port=port, use_reloader=use_reloader)


