import os
import logging
from flask import Flask, request, jsonify

from peoples_coin.routes import register_routes

from peoples_coin.extensions import (
    db,
    migrate,
    cors,
    limiter,
    swagger,
    make_celery,
    redis_client  # Redis client imported here
)

from peoples_coin.systems.immune_system import immune_system
from peoples_coin.systems.cognitive_system import cognitive_system
from peoples_coin.systems.endocrine_system import endocrine_system
from peoples_coin.systems.circulatory_system import circulatory_system
from peoples_coin.consensus import Consensus

from peoples_coin.utils.recaptcha import verify_recaptcha

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    """Creates and configures the Flask application."""
    app = Flask(__name__, instance_relative_config=True)

    try:
        # Detect if running on Google Cloud Run
        if os.environ.get("K_SERVICE"):
            db_user = os.environ.get("DB_USER")
            db_pass = os.environ.get("DB_PASS")
            db_name = os.environ.get("DB_NAME")
            instance_connection_name = os.environ.get("INSTANCE_CONNECTION_NAME")
            db_uri = (
                f"postgresql+pg8000://{db_user}:{db_pass}@/{db_name}"
                f"?unix_sock=/cloudsql/{instance_connection_name}/.s.PGSQL.5432"
            )
            logger.info("✅ App configured for Cloud Run.")
        else:
            # Local dev environment: expect DATABASE_URL to be set
            db_uri = os.environ.get("DATABASE_URL")
            if not db_uri:
                raise ValueError("DATABASE_URL is not set for local development.")
            logger.info("✅ App configured for local development.")

        # Load config from environment variables — no hardcoded URLs
        app.config.from_mapping(
            SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret"),
            SQLALCHEMY_DATABASE_URI=db_uri,
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            CELERY_BROKER_URL=os.environ.get("CELERY_BROKER_URL"),
            CELERY_RESULT_BACKEND=os.environ.get("CELERY_RESULT_BACKEND"),
            RECAPTCHA_SECRET_KEY=os.environ.get("RECAPTCHA_SECRET_KEY"),
            # Redis client URL — reuse Celery broker URL env var
            REDIS_URL=os.environ.get("CELERY_BROKER_URL")
        )

    except Exception as e:
        logger.critical(f"🚨 FAILED TO CONFIGURE DATABASE: {e}")
        raise

    # Initialize Flask extensions
    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app)
    limiter.init_app(app)
    swagger.init_app(app)
    redis_client.init_app(app)  # Redis client init here
    logger.info("✅ Core Flask extensions initialized.")

    # Initialize Celery and custom systems inside app context
    with app.app_context():
        if app.config.get("CELERY_BROKER_URL"):
            make_celery(app)
            logger.info("✅ Celery initialized.")

        immune_system.init_app(app)
        cognitive_system.init_app(app)
        endocrine_system.init_app(app, ai_processor_func=lambda x: print(f"Processing AI for {x}"))

        consensus_instance = Consensus()
        consensus_instance.init_app(app, db_instance=db, redis_instance=redis_client)

        circulatory_system.init_app(app, consensus_instance=consensus_instance)

        logger.info("✅ All custom systems initialized.")

        # Start background threads for systems that need it
        immune_system.start()
        cognitive_system.start()
        endocrine_system.start()
        logger.info("✅ All custom system background threads started.")

    # Register blueprints
    register_routes(app)
    logger.info("✅ Blueprints registered successfully.")

    # Health check endpoint
    @app.route("/health")
    def health():
        return {"status": "ok"}, 200

    logger.info("🚀 Flask app created successfully!")
    return app

