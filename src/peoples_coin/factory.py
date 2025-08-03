import os
import logging
from flask import Flask
from flask_cors import CORS

from peoples_coin.extensions import db, migrate, cors, limiter, swagger, make_celery

def create_app():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    try:
        app = Flask(__name__, instance_relative_config=True)

        # Load config from environment or defaults
        app.config.from_mapping(
            SECRET_KEY=os.environ.get("SECRET_KEY", "a-strong-dev-secret-key"),
            SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL"),
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},

            # Celery config example (adjust as needed)
            CELERY_BROKER_URL=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
            CELERY_RESULT_BACKEND=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
        )
        logger.info("✅ App configured.")

        # Initialize extensions with app
        db.init_app(app)
        migrate.init_app(app, db)
        cors.init_app(app, origins=[
            "https://brightacts.com",
            "https://www.brightacts.com",
            "https://brightacts-frontend-50f58.web.app",
            "https://brightacts-frontend-50f58.firebaseapp.com",
            r"http://localhost:\d+",
        ], supports_credentials=True)
        limiter.init_app(app)
        swagger.init_app(app)
        logger.info("✅ Extensions initialized.")

        # Initialize Celery app context binding
        celery = make_celery(app)
        logger.info("✅ Celery initialized.")

        # Register blueprints
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
        raise

