import os
import logging
import uuid
import http
import secrets
import signal
from functools import wraps
from datetime import datetime, timezone

from flask import Flask, request, jsonify, g, current_app, Blueprint, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from pydantic import BaseModel, ValidationError, Field
from flasgger import Swagger, swag_from
import click

# ==============================================================================
# 1. Centralized Configuration
# ==============================================================================
class Config:
    """Base configuration settings loaded from environment variables."""
    SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    # --- Database (Set in factory from POSTGRES_DB_URI) ---
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Redis & Rate Limiting ---
    # One Redis URL for all services, loaded from environment
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/1")
    RATELIMIT_DEFAULT = "50 per hour;10 per minute"

    # --- API Keys ---
    API_KEYS = set(os.getenv("SKELETON_API_KEYS", "skeletonkey,defaultkey").split(","))
    
    # --- Swagger UI ---
    SWAGGER = {
        'title': "People's Coin API",
        'uiversion': 3,
        'description': "API for the core systems of The People's Coin.",
    }

# ==============================================================================
# 2. Pydantic Input Models
# ==============================================================================
class NodeRegistrationModel(BaseModel):
    node_id: str = Field(..., min_length=3, max_length=64)
    ip_address: str
    metadata: dict = Field(default_factory=dict)


# ==============================================================================
# 3. Decorators
# ==============================================================================
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if not api_key or not any(secrets.compare_digest(api_key, key) for key in current_app.config["API_KEYS"]):
            logging.warning(f"Unauthorized access attempt from {request.remote_addr}")
            abort(http.HTTPStatus.UNAUTHORIZED, description="Invalid or missing API key")
        g.api_key = api_key
        return f(*args, **kwargs)
    return decorated

def validate_with(model: BaseModel):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                g.validated_data = model(**request.get_json(force=True))
            except ValidationError as e:
                return jsonify(error="Validation error", details=e.errors()), http.HTTPStatus.BAD_REQUEST
            except Exception:
                return jsonify(error="Malformed JSON request"), http.HTTPStatus.BAD_REQUEST
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ==============================================================================
# 4. API Blueprint
# ==============================================================================
api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

@api_bp.route("/health", methods=["GET"])
def health():
    """Basic health check to confirm the service is running."""
    return jsonify(status="healthy"), http.HTTPStatus.OK

@api_bp.route("/readiness", methods=["GET"])
def readiness():
    """Checks if the service and its dependencies (like the DB) are ready."""
    from peoples_coin.extensions import db
    try:
        with db.engine.connect() as connection:
            connection.execute("SELECT 1")
        return jsonify(status="ready"), http.HTTPStatus.OK
    except Exception as e:
        logging.error(f"Readiness check failed: {e}", exc_info=True)
        return jsonify(status="error", message="Not ready"), http.HTTPStatus.SERVICE_UNAVAILABLE

@api_bp.route("/register_node", methods=["POST"])
@require_api_key
@validate_with(NodeRegistrationModel)
def register_node():
    node: NodeRegistrationModel = g.validated_data
    logging.info(f"Node registered: {node.node_id}")
    # TODO: Implement persistence to ConsensusNode model
    return jsonify(status="success", node_id=node.node_id), http.HTTPStatus.CREATED

@api_bp.route("/nodes", methods=["GET"])
@require_api_key
def list_nodes():
    # TODO: Implement listing from ConsensusNode model
    nodes = [{"node_id": "stub_node_1", "ip": "192.168.1.10"}]
    return jsonify(status="success", nodes=nodes), http.HTTPStatus.OK


# ==============================================================================
# 5. Flask App Factory
# ==============================================================================
def create_app(config_object=Config) -> Flask:
    """Creates, configures, and returns the Flask application instance."""
    app = Flask(__name__)
    app.config.from_object(config_object)
    
    # Set the DB URI from the environment variable, falling back to SQLite for local dev
    db_uri = os.getenv('POSTGRES_DB_URI', 'sqlite:///../instance/app.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri

    # Configure logging
    logging.basicConfig(level=app.config["LOG_LEVEL"], format="[%(asctime)s] %(levelname)s %(name)s %(message)s")
    logger = logging.getLogger(__name__)

    # --- Initialize Extensions (Non-blocking) ---
    from peoples_coin.extensions import db, immune_system, consensus_instance, circulatory_system, cognitive_system
    
    db.init_app(app)
    CORS(app)
    Swagger(app)
    
    # Initialize the rate limiter lazily. It will connect on the first request.
    Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=[app.config['RATELIMIT_DEFAULT']],
        storage_uri=app.config['REDIS_URL']
    )
    logger.info("Rate limiting configured.")

    # --- Initialize Custom Systems (now non-blocking) ---
    immune_system.init_app(app)
    cognitive_system.init_app(app)
    consensus_instance.init_app(app, db)
    circulatory_system.init_app(app, db, consensus_instance)
    # ... initialize other systems as needed ...

    # --- Register Blueprints ---
    app.register_blueprint(api_bp)
    # ... register your other blueprints ...

    # --- Register CLI Commands ---
    register_cli_commands(app)

    # --- Start Background Systems ---
    # This block runs after the app is fully configured, before returning.
    with app.app_context():
        immune_system.start()
        cognitive_system.start()
        # ... start other background systems ...
    
    logger.info("✅ Application startup sequence complete.")
    return app

def register_cli_commands(app: Flask):
    """Registers one-time setup commands."""
    from peoples_coin.extensions import consensus_instance
    
    @app.cli.command("create-genesis-block")
    def create_genesis_block_command():
        """Checks for and creates the genesis block."""
        click.echo("Checking for genesis block...")
        try:
            with app.app_context():
                consensus_instance.create_genesis_block_if_needed()
            click.secho("✅ Genesis block check complete.", fg="green")
        except Exception as e:
            click.secho(f"❌ Error creating genesis block: {e}", fg="red")

# ==============================================================================
# 6. Main (for Local Development)
# ==============================================================================
if __name__ == '__main__':
    # Use python-dotenv for local development
    from dotenv import load_dotenv
    load_dotenv()

    app = create_app()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
