import os
import logging
from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

# Initialize extensions globally so they can be imported anywhere
db = SQLAlchemy()

def create_app():
    # Use /tmp/instance to avoid permission errors (good for Cloud Run or containers)
    instance_path = "/tmp/instance"
    os.makedirs(instance_path, exist_ok=True)

    # Create Flask app instance with writable instance_path
    app = Flask(__name__, instance_path=instance_path)

    # Load config from environment variables or use defaults
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///local.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret"),
        SQLALCHEMY_ENGINE_OPTIONS={
            "pool_pre_ping": True,  # Handle stale DB connections gracefully
        },
    )

    # Setup CORS with specific allowed origins
    CORS(
        app,
        resources={
            r"/*": {
                "origins": [
                    "https://brightacts.com",
                    "https://www.brightacts.com",
                    "http://localhost:3000",
                ]
            }
        },
        supports_credentials=True,
    )

    # Setup logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("✅ Flask app instance created and configured.")

    # Initialize extensions with app
    db.init_app(app)

    # Import and register blueprints here
    try:
        # Import the register_routes function and call it to register blueprints
        from peoples_coin.routes import register_routes
        register_routes(app)
        logger.info("✅ Blueprints registered.")
    except ImportError as e:
        logger.warning(f"⚠️ Failed to register blueprints. Reason: {e}")

    # Health check endpoint
    @app.route("/health")
    def health():
        return {"status": "ok"}, 200

    return app

