import os
import logging
from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

# Initialize extensions
db = SQLAlchemy()

def create_app():
    # Use /tmp/instance to avoid permission errors on Cloud Run
    instance_path = "/tmp/instance"
    os.makedirs(instance_path, exist_ok=True)

    # Create Flask app instance with writable instance_path
    app = Flask(__name__, instance_path=instance_path)

    # Load config from environment or fallback
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///local.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret"),
        SQLALCHEMY_ENGINE_OPTIONS={
            "pool_pre_ping": True,  # Helps handle stale DB connections
        },
    )

    # Setup CORS
    CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("✅ Flask app instance created and configured.")

    # Initialize extensions
    db.init_app(app)

    # Register all blueprints using your register_routes function
    try:
        from peoples_coin.routes import register_routes
        register_routes(app)
        logger.info("✅ Blueprints registered.")
    except ImportError as e:
        logger.warning("⚠️ Failed to register blueprints. Reason: %s", str(e))

    # Basic health check endpoint
    @app.route("/health")
    def health():
        return {"status": "ok"}, 200

    return app

