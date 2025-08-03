import os
import logging
from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

# Initialize extensions globally
db = SQLAlchemy()

def create_app():
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    try:
        # Create Flask app instance
        app = Flask(__name__, instance_relative_config=True)

        # Load configuration
        app.config.from_mapping(
            SECRET_KEY=os.environ.get("SECRET_KEY", "a-strong-dev-secret-key"),
            SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL"),
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        )
        logger.info("✅ App configured.")

        # Setup CORS
        allowed_origins = [
            "https://brightacts.com",
            "https://www.brightacts.com",
            "https://brightacts-frontend-50f58.web.app",
            "https://brightacts-frontend-50f58.firebaseapp.com",
        ]
        CORS(app, origins=allowed_origins + [r"http://localhost:\d+"], supports_credentials=True)
        logger.info("✅ CORS configured.")

        # Initialize extensions
        db.init_app(app)
        logger.info("✅ Database initialized.")

        # Import and register blueprints
        from peoples_coin.routes import register_routes
        register_routes(app)
        logger.info("✅ Blueprints registered.")

        # Health check endpoint
        @app.route("/health")
        def health():
            return {"status": "ok"}, 200

        logger.info("🚀 Flask app created successfully!")
        return app

    except Exception as e:
        logger.exception(f"🚨 CRITICAL ERROR DURING APP CREATION: {e}")
        # Re-raise the exception to ensure the server process fails as expected
        raise
