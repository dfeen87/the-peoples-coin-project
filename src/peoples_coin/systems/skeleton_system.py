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
    SECRET_KEY = os.getenv("SECRET_KEY", "a-very-secret-key")
    API_KEYS = set(os.getenv("SKELETON_API_KEYS", "skeletonkey,defaultkey").split(","))
    DEBUG = os.getenv("SKELETON_DEBUG", "false").lower() == "true"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    RATELIMIT_DEFAULT = "50 per hour;10 per minute"
    REDIS_URI = f"redis://{os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', '6379')}/{os.getenv('REDIS_DB_SKELETON', '2')}"
    SWAGGER = {
        'title': "People's Coin Skeleton System API",
        'uiversion': 3,
        'description': "API for the core skeleton system of The People's Coin.",
        'contact': {
            'name': 'API Support',
            'email': 'support@example.com',
        },
        'license': {'name': 'MIT', 'url': 'https://opensource.org/licenses/MIT'},
    }

# ==============================================================================
# 2. Logging Setup
# ==============================================================================
logging.basicConfig(
    level=Config.LOG_LEVEL,
    format="[%(asctime)s] %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger(__name__)

# ==============================================================================
# 3. Pydantic Input Models
# ==============================================================================
class NodeRegistrationModel(BaseModel):
    node_id: str = Field(..., min_length=3, max_length=64)
    ip_address: str
    metadata: dict = Field(default_factory=dict)

class TransactionModel(BaseModel):
    key: str
    value: str
    contributor: str

# ==============================================================================
# 4. Decorators
# ==============================================================================
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if not api_key or not any(secrets.compare_digest(api_key, key) for key in current_app.config["API_KEYS"]):
            logger.warning(f"Unauthorized access attempt from {request.remote_addr}")
            abort(http.HTTPStatus.UNAUTHORIZED, description="Invalid or missing API key")
        g.api_key = api_key
        return f(*args, **kwargs)
    return decorated

def validate_with(model: BaseModel):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                data = request.get_json(force=True)
                g.validated_data = model(**data)
            except ValidationError as e:
                logger.warning(f"Validation failed ({model.__name__}): {e.errors()}")
                return jsonify(status="error", error="Validation error", details=e.errors()), http.HTTPStatus.BAD_REQUEST
            except Exception as e:
                logger.exception("Invalid JSON or malformed request.")
                return jsonify(status="error", error="Malformed request", details=str(e)), http.HTTPStatus.BAD_REQUEST
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ==============================================================================
# 5. Blueprint
# ==============================================================================
api_bp = Blueprint("api", __name__)

@api_bp.route("/", methods=["GET"])
def index() -> tuple[Response, int]:
    return jsonify(status="success", message="Welcome to The People's Coin Skeleton System"), http.HTTPStatus.OK

@api_bp.route("/health", methods=["GET"])
def health() -> tuple[Response, int]:
    return jsonify(status="success", timestamp=datetime.now(timezone.utc).isoformat()), http.HTTPStatus.OK

@api_bp.route("/readiness", methods=["GET"])
def readiness() -> tuple[Response, int]:
    try:
        Redis.from_url(current_app.config['REDIS_URI'], socket_connect_timeout=1).ping()
        return jsonify(status="success", message="ready"), http.HTTPStatus.OK
    except RedisError:
        logger.warning("Readiness check: Redis unavailable.")
        return jsonify(status="error", message="Redis unavailable"), http.HTTPStatus.SERVICE_UNAVAILABLE

@api_bp.route("/register_node", methods=["POST"])
@require_api_key
@validate_with(NodeRegistrationModel)
@swag_from({
    'tags': ['Nodes'],
    'parameters': [{'name': 'body', 'in': 'body', 'schema': NodeRegistrationModel.schema(), 'required': True}],
    'responses': {
        201: {'description': 'Node registered'},
        400: {'description': 'Validation error'},
        401: {'description': 'Unauthorized'},
        429: {'description': 'Rate limit exceeded'}
    }
})
def register_node() -> tuple[Response, int]:
    node: NodeRegistrationModel = g.validated_data
    logger.info(f"Node registered: {node.node_id} by API key ending in ...{g.api_key[-4:]}")
    return jsonify(status="success", node_id=node.node_id), http.HTTPStatus.CREATED

@api_bp.route("/nodes", methods=["GET"])
@require_api_key
def list_nodes() -> tuple[Response, int]:
    nodes = [{"node_id": "node1_stub", "ip": "192.168.1.1"}, {"node_id": "node2_stub", "ip": "192.168.1.2"}]
    return jsonify(status="success", nodes=nodes), http.HTTPStatus.OK

@api_bp.route("/validate_transaction", methods=["POST"])
@require_api_key
@validate_with(TransactionModel)
def validate_transaction_endpoint() -> tuple[Response, int]:
    def mock_validate_transaction(data):
        return True, {"message": "Transaction appears valid."}

    is_valid, result = mock_validate_transaction(g.validated_data.dict())
    if not is_valid:
        return jsonify(status="error", valid=False, errors=result), http.HTTPStatus.BAD_REQUEST
    return jsonify(status="success", valid=True, data=result), http.HTTPStatus.OK

# ==============================================================================
# 6. Flask App Factory
# ==============================================================================
def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    CORS(app)
    Swagger(app, config=app.config['SWAGGER'])

    # Rate limiter
    try:
        Redis.from_url(app.config['REDIS_URI'], socket_connect_timeout=2).ping()
        limiter = Limiter(key_func=get_remote_address, storage_uri=app.config['REDIS_URI'])
        logger.info("Rate limiting with Redis.")
    except RedisError as e:
        limiter = Limiter(key_func=get_remote_address)  # fallback
        logger.warning(f"Redis unavailable, fallback rate limiting: {e}")
    limiter.init_app(app)

    @app.before_request
    def add_correlation_id():
        g.correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))

    app.register_blueprint(api_bp, url_prefix="/api/v1")

    for code, msg in {
        400: "Bad request",
        401: "Unauthorized",
        404: "Not found",
        429: "Rate limit exceeded",
        500: "Internal server error",
    }.items():
        app.register_error_handler(code, lambda e, msg=msg, code=code: (
            jsonify(status="error", error=msg, details=getattr(e, 'description', msg)),
            code
        ))

    def handle_shutdown_signal(signum, frame):
        logger.info(f"Shutdown signal ({signum}) received. Cleaning up.")
        exit(0)

    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    return app

# ==============================================================================
# 7. Main
# ==============================================================================
if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("SKELETON_PORT", 5002))
    use_reloader = app.config["DEBUG"]
    logger.info(f"Skeleton System API running on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, use_reloader=use_reloader)

