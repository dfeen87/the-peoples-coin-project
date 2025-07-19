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

from peoples_coin.extensions import db, immune_system
from peoples_coin.consensus import Consensus, consensus_instance
from peoples_coin.systems.metabolic_systems import metabolic_bp
from peoples_coin.systems.nervous_system import nervous_bp
from peoples_coin.systems.circulatory_system import CirculatorySystem, circulatory_system
from peoples_coin.systems.reproductive_system import reproductive_bp

from peoples_coin.services.goodwill_service import goodwill_service
from peoples_coin.services.governance_service import governance_service
from peoples_coin.services.user_service import user_service


# ==============================================================================
# 1. Centralized Configuration
# ==============================================================================
class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
    API_KEYS = set(os.getenv("SKELETON_API_KEYS", "skeletonkey,defaultkey").split(","))
    DEBUG = os.getenv("SKELETON_DEBUG", "false").lower() == "true"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    RATELIMIT_DEFAULT = "50 per hour;10 per minute"
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = os.getenv('REDIS_PORT', '6379')
    REDIS_DB_SKELETON = os.getenv('REDIS_DB_SKELETON', '2')
    REDIS_URI = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB_SKELETON}"
    SWAGGER = {
        'title': "People's Coin Skeleton System API",
        'uiversion': 3,
        'description': "API for the core skeleton system of The People's Coin.",
        'contact': {
            'name': 'API Support',
            'email': 'support@example.com',
        },
        'license': {'name': 'MIT', 'url': 'https://opensource.org/licenses/MIT'},
        'schemes': ['http', 'https']
    }
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://user:password@localhost:5432/peoplescoin_db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    POW_DIFFICULTY = os.getenv("POW_DIFFICULTY", "0000")
    MINTER_WALLET_ADDRESS = os.getenv("MINTER_WALLET_ADDRESS", "0x0000000000000000000000000000000000000000")


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


# ==============================================================================
# 4. Decorators
# ==============================================================================
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if not api_key or not any(secrets.compare_digest(api_key, key) for key in current_app.config["API_KEYS"]):
            logger.warning(f"Unauthorized access attempt from {request.remote_addr} (API Key missing or invalid).")
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
# 5. API Blueprint for Skeleton System
# ==============================================================================
skeleton_api_bp = Blueprint("skeleton_api", __name__, url_prefix="/api/v1")


@skeleton_api_bp.route("/", methods=["GET"])
def index() -> tuple[Response, int]:
    return jsonify(status="success", message="Welcome to The People's Coin Skeleton System API"), http.HTTPStatus.OK


@skeleton_api_bp.route("/health", methods=["GET"])
def health() -> tuple[Response, int]:
    return jsonify(status="success", timestamp=datetime.now(timezone.utc).isoformat()), http.HTTPStatus.OK


@skeleton_api_bp.route("/readiness", methods=["GET"])
def readiness() -> tuple[Response, int]:
    try:
        Redis.from_url(current_app.config['REDIS_URI'], socket_connect_timeout=1).ping()
        with db.session() as session:
            session.execute("SELECT 1")
        return jsonify(status="success", message="ready"), http.HTTPStatus.OK
    except (RedisError, Exception) as e:
        logger.warning(f"Readiness check failed: {e}")
        return jsonify(status="error", message="Not ready", details=str(e)), http.HTTPStatus.SERVICE_UNAVAILABLE


@skeleton_api_bp.route("/register_node", methods=["POST"])
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
    # TODO: Implement persistence to ConsensusNode model/table with session scope
    return jsonify(status="success", node_id=node.node_id), http.HTTPStatus.CREATED


@skeleton_api_bp.route("/nodes", methods=["GET"])
@require_api_key
def list_nodes() -> tuple[Response, int]:
    # TODO: Implement listing from ConsensusNode table using DB session
    nodes = [
        {"node_id": "node1_stub", "ip": "192.168.1.1"},
        {"node_id": "node2_stub", "ip": "192.168.1.2"},
    ]
    return jsonify(status="success", nodes=nodes), http.HTTPStatus.OK


# ==============================================================================
# 6. Flask App Factory (Core Application Setup)
# ==============================================================================
def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Enable CORS and Swagger UI
    CORS(app)
    Swagger(app, config=app.config['SWAGGER'])

    # Initialize extensions
    db.init_app(app)

    # Initialize core systems (order matters for dependencies)
    consensus_instance.init_app(app, db)
    circulatory_system.init_app(app, db, consensus_instance)
    immune_system.init_app(app)

    # Initialize service layer instances
    goodwill_service.init_app(app, db)
    governance_service.init_app(app, db)
    user_service.init_app(app, db)

    # Rate limiter setup with Redis fallback
    try:
        redis_client = Redis.from_url(app.config['REDIS_URI'], socket_connect_timeout=2)
        redis_client.ping()
        limiter = Limiter(
            key_func=get_remote_address,
            storage_uri=app.config['REDIS_URI'],
            app=app,
            default_limits=[app.config['RATELIMIT_DEFAULT']],
        )
        logger.info("Rate limiting enabled with Redis backend.")
    except RedisError as e:
        limiter = Limiter(
            key_func=get_remote_address,
            app=app,
            default_limits=[app.config['RATELIMIT_DEFAULT']],
        )
        logger.warning(f"Redis unavailable, fallback to in-memory rate limiting: {e}")

    @app.before_request
    def add_correlation_id():
        g.correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))

    # Register blueprints
    app.register_blueprint(skeleton_api_bp)
    app.register_blueprint(metabolic_bp)
    app.register_blueprint(nervous_bp)
    app.register_blueprint(reproductive_bp)

    # Register error handlers with closure to avoid late binding issue
    def make_error_handler(msg, code):
        def handler(e):
            return jsonify(status="error", error=msg, details=getattr(e, 'description', msg)), code
        return handler

    for code, msg in {
        400: "Bad request",
        401: "Unauthorized",
        404: "Not found",
        429: "Rate limit exceeded",
        500: "Internal server error",
    }.items():
        app.register_error_handler(code, make_error_handler(msg, code))

    # Graceful shutdown handler
    def handle_shutdown_signal(signum, frame):
        logger.info(f"Shutdown signal ({signum}) received. Cleaning up.")
        immune_system.stop()
        # If you have other background workers, stop them here as well
        exit(0)

    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    # Ensure genesis block and start background tasks if needed
    with app.app_context():
        consensus_instance.create_genesis_block_if_needed()
        # endocrine_system.start() # Uncomment if using endocrine background workers

    return app


# ==============================================================================
# 7. Main (for Local Development/Debugging)
# ==============================================================================
if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()

    app = create_app()

    port = int(os.environ.get('PORT', 5000))
    use_reloader = app.config["DEBUG"]
    logger.info(f"Skeleton System API running on http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=use_reloader)

