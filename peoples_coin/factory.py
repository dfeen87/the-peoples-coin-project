import os
import logging
from flask import Flask

from peoples_coin.extensions import db, migrate, cors, limiter, swagger, make_celery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    """Creates and configures the Flask application."""
    try:
        app = Flask(__name__, instance_relative_config=True)

        # --- Dynamic Database URI Configuration ---
        database_url = None
        
        if os.environ.get("K_SERVICE"):
            logger.info("Cloud Run environment detected. Configuring for Cloud SQL with Auth Proxy.")
            db_user = os.environ.get("DB_USER", "postgres")
            db_pass = os.environ.get("DB_PASS", "NDfcIdlRk0")
            db_name = os.environ.get("DB_NAME", "brightacts")
            instance_connection_name = os.environ.get("INSTANCE_CONNECTION_NAME", "heroic-tide-428421-q7:us-central1:peoples-coin-cluster-final")
            
            if not all([db_user, db_pass, db_name, instance_connection_name]):
                 raise ValueError("Missing database configuration for Cloud Run.")

            database_url = (
                f"postgresql+psycopg2://{db_user}:{db_pass}@/{db_name}"
                f"?host=/cloudsql/{instance_connection_name}"
            )
        else:
            logger.info("Local environment detected. Using DATABASE_URL.")
            database_url = os.environ.get("DATABASE_URL")
            if not database_url:
                raise ValueError("DATABASE_URL environment variable is not set for local development.")

        # --- App Configuration ---
        REDIS_HOST = os.environ.get("REDIS_HOST", "10.128.0.12")
        CELERY_URL = os.environ.get("CELERY_BROKER_URL", f"redis://{REDIS_HOST}:6379/0")

        app.config.from_mapping(
            SECRET_KEY=os.environ.get("SECRET_KEY", "a-strong-dev-secret-key"),
            SQLALCHEMY_DATABASE_URI=database_url,
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
            CELERY_BROKER_URL=CELERY_URL,
            CELERY_RESULT_BACKEND=CELERY_URL,
            RATELIMIT_STORAGE_URI=CELERY_URL,
            RECAPTCHA_SECRET_KEY=os.environ.get("RECAPTCHA_SECRET_KEY_PROD", "6LeE0pQrAAAAALSMkV1cRCcyJZopTZJYKP1NbGAf"),
        )
        logger.info("✅ App configured.")

        # --- Initialize Extensions ---
        db.init_app(app)
        migrate.init_app(app, db)
        
        cors.init_app(
            app,
            origins=[
                "https://brightacts.com",
                "https://www.brightacts.com",
                "https://brightacts-frontend-50f58.web.app",
                "https://brightacts-frontend-50f58.firebaseapp.com",
                "https://peoples-coin-service-105378934751.us-central1.run.app",
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            ],
            supports_credentials=True,
            allow_headers=["Content-Type", "Authorization"],
            expose_headers=["Content-Type", "Authorization"],
            methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        )
        
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

