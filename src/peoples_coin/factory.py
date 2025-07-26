# src/peoples_coin/factory.py
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import atexit
import signal
import http # Import http for HTTPStatus

import click
from flask import Flask, jsonify
import firebase_admin
from firebase_admin import credentials
from celery import Celery # Ensure Celery is imported for type hinting

from peoples_coin.config import Config
from peoples_coin.extensions import db, migrate, cors, limiter, swagger, celery
from peoples_coin.routes.api import api_bp # Ensure api_bp is imported

# Set up a logger for the factory
logger = logging.getLogger(__name__)

def create_app(config_object=Config) -> Flask:
    """Creates and configures a new Flask application instance."""
    app = Flask(__name__)
    app.config.from_object(config_object)

    logger.info("Starting Flask application creation...")

    try:
        setup_logging(app)
        logger.info("Logging setup complete.")
    except Exception as e:
        logger.error(f"Error during logging setup: {e}", exc_info=True)
        raise

    try:
        init_extensions(app)
        logger.info("Flask extensions initialized.")
    except Exception as e:
        logger.error(f"Error during extension initialization: {e}", exc_info=True)
        raise

    try:
        init_firebase_admin(app)
        logger.info("Firebase Admin SDK initialization attempted.")
    except Exception as e:
        logger.error(f"Error during Firebase Admin SDK initialization: {e}", exc_info=True)
        raise

    # Register components
    try:
        app.register_blueprint(api_bp)
        logger.info("API blueprint registered.")
    except Exception as e:
        logger.error(f"Error registering API blueprint: {e}", exc_info=True)
        raise

    try:
        register_cli_commands(app)
        logger.info("CLI commands registered.")
    except Exception as e:
        logger.error(f"Error registering CLI commands: {e}", exc_info=True)
        raise

    try:
        register_shutdown_handlers(app)
        logger.info("Shutdown handlers registered.")
    except Exception as e:
        logger.error(f"Error registering shutdown handlers: {e}", exc_info=True)
        raise

    # --- NEW: Root Health Check endpoint for early startup probe ---
    @app.route('/healthz_root', methods=['GET'])
    def healthz_root():
        """Basic health check at root for early startup probe."""
        logger.info("Received /healthz_root probe.")
        return "OK", http.HTTPStatus.OK
    # --- END NEW ---

    logger.info("✅ Application factory setup complete. Returning app instance.")
    return app

def init_extensions(app: Flask):
    """Initialize all Flask extensions."""
    logger.info("Initializing extensions...")
    try:
        db.init_app(app)
        logger.info("SQLAlchemy DB extension initialized.")
    except Exception as e:
        logger.error(f"Error initializing DB extension: {e}", exc_info=True)
        raise

    try:
        migrate.init_app(app, db)
        logger.info("Flask-Migrate extension initialized.")
    except Exception as e:
        logger.error(f"Error initializing Flask-Migrate extension: {e}", exc_info=True)
        raise

    try:
        # Restore original CORS config as Secret Manager is now used
        cors.init_app(app, resources={r"/api/*": {"origins": "https://brightacts.com"}})
        logger.info("Flask-CORS extension initialized for origin: https://brightacts.com")
    except Exception as e:
        logger.error(f"Error initializing Flask-CORS extension: {e}", exc_info=True)
        raise

    try:
        limiter.init_app(app)
        logger.info("Flask-Limiter extension initialized.")
    except Exception as e:
        logger.error(f"Error initializing Flask-Limiter extension: {e}", exc_info=True)
        raise

    try:
        swagger.init_app(app)
        logger.info("Flasgger (Swagger) extension initialized.")
    except Exception as e:
        logger.error(f"Error initializing Flasgger (Swagger) extension: {e}", exc_info=True)
        raise

    try:
        configure_celery(app, celery)
        logger.info("Celery configured.")
    except Exception as e:
        logger.error(f"Error configuring Celery: {e}", exc_info=True)
        raise
    logger.info("All extensions initialization attempted.")

def configure_celery(app: Flask, celery_instance: Celery):
    """Configures Celery to run within the Flask application context."""
    logger.info("Configuring Celery instance...")
    try:
        celery_instance.conf.broker_url = app.config.get("CELERY_BROKER_URL")
        celery_instance.conf.result_backend = app.config.get("CELERY_RESULT_BACKEND")
        celery_instance.conf.update(app.config)
        logger.info(f"Celery broker URL: {celery_instance.conf.broker_url}")
        logger.info(f"Celery result backend: {celery_instance.conf.result_backend}")
    except Exception as e:
        logger.error(f"Error setting Celery config: {e}", exc_info=True)
        raise

    class ContextTask(celery_instance.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_instance.Task = ContextTask
    app.extensions['celery'] = celery_instance
    logger.info("Celery ContextTask set.")

def setup_logging(app: Flask):
    """Configures logging for the application."""
    logger.info("Setting up logging...")
    log_level = app.config.get("LOG_LEVEL", "INFO") # Default to INFO if not set
    logging.root.handlers.clear()
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    
    os.makedirs(app.instance_path, exist_ok=True)
    file_handler = RotatingFileHandler(
        os.path.join(app.instance_path, 'app.log'),
        maxBytes=5 * 1024 * 1024, backupCount=5
    )
    file_handler.setFormatter(formatter)
    
    logging.basicConfig(level=log_level, handlers=[stream_handler, file_handler])
    logging.getLogger(__name__).info(f"Logging configured with level: {log_level}")

def init_firebase_admin(app: Flask):
    """Initializes the Firebase Admin SDK."""
    logger.info("Attempting Firebase Admin SDK initialization...")
    path = app.config.get("FIREBASE_CREDENTIALS_PATH")
    if not path:
        logger.error("FIREBASE_CREDENTIALS_PATH is not set in app config. Firebase Admin SDK will not initialize.")
        return # Do not attempt to initialize if path is missing

    if not firebase_admin._apps:
        if os.path.exists(path):
            try:
                cred = credentials.Certificate(path)
                firebase_admin.initialize_app(cred)
                logger.info("✅ Firebase Admin SDK initialized successfully.")
            except Exception as e:
                logger.error(f"❌ Error initializing Firebase Admin SDK with credentials at {path}: {e}", exc_info=True)
                raise # Re-raise to ensure crash is visible
        else:
            logger.error(f"❌ Firebase credentials file NOT FOUND at {path}. Firebase Admin SDK will not initialize.")
            raise FileNotFoundError(f"Firebase credentials file not found: {path}") # Re-raise to see the crash

def register_cli_commands(app: Flask):
    """Registers CLI commands for the application."""
    logger.info("Registering CLI commands...")
    @app.cli.command("start-systems")
    def start_systems_command():
        """Starts the background systems (placeholder)."""
        click.echo("Starting background systems...")
        click.secho("✅ Systems would be running now.", fg="green")
    logger.info("CLI commands registration attempted.")

def register_shutdown_handlers(app: Flask):
    """Registers graceful shutdown handlers."""
    logger.info("Registering shutdown handlers...")
    def shutdown_systems(*args):
        logger.warning("⚠️ Initiating graceful shutdown...")
        logger.info("✅ Background systems shut down.")

    atexit.register(shutdown_systems)
    signal.signal(signal.SIGTERM, shutdown_systems)
    signal.signal(signal.SIGINT, shutdown_systems)
    logger.info("Shutdown handlers registration attempted.")

# The __main__ block for SystemController is commented out in its own file.
# This factory.py does not have a __main__ block that runs the Flask app directly.

