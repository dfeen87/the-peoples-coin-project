import os
import logging
from flask import Flask

from peoples_coin.extensions import db, migrate, cors, limiter, swagger, make_celery

# Set up logger at the module level
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    """Creates and configures the Flask application."""
    try:
        app = Flask(__name__, instance_relative_config=True)

        # --- Configuration ---
        # Set a robust, Docker-friendly default for the Redis host
        REDIS_HOST = os.environ.get("REDIS_HOST", "redis")

        # Load config from environment variables or the defaults provided
        app.config.from_mapping(
            SECRET_KEY=os.environ.get("SECRET_KEY", "a-strong-dev-secret-key"),
            
            # This now correctly reads from the DATABASE_URL environment variable
            SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL"),
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},

            # Corrected and Docker-friendly Celery configuration
            CELERY_BROKER_URL=os.environ.get("CELERY_BROKER_URL", f"redis://{REDIS_HOST}:6379/0"),
            CELERY_RESULT_BACKEND=os.environ.get("CELERY_RESULT_BACKEND", f"redis://{REDIS_HOST}:6379/0"),
        )
        logger.info("✅ App configured.")

        # --- Initialize Extensions ---
        db.init_app(app)
        migrate.init_app(app, db)
        cors.init_app(app, origins=[
            "https://brightacts.com",
            "https://www.brightacts.com",
            "https://brightacts-frontend-50f58.web.app",
            "https://brightacts-frontend-50f58.firebaseapp.com",
            # This regex correctly allows any port on localhost
            r"http://localhost:\d+",
        ], supports_credentials=True)
        limiter.init_app(app)
        swagger.init_app(app)
        logger.info("✅ Extensions initialized.")

        # --- Initialize Celery ---
        make_celery(app)
        logger.info("✅ Celery initialized.")

        # --- Register Blueprints ---
        from peoples_coin.routes import register_routes
        register_routes(app)
        logger.info("✅ Blueprints registered.")

        # --- Health Check Endpoint ---
        @app.route("/health")
        def health():
            return {"status": "ok"}, 200

        logger.info("🚀 Flask app created successfully!")
        return app

    except Exception as e:
        logger.exception(f"🚨 CRITICAL ERROR DURING APP CREATION: {e}")
        raise
