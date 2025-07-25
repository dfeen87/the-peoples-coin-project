import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import atexit
import signal

import click
from flask import Flask, jsonify
import firebase_admin
from firebase_admin import credentials
# Import Celery for type hinting in configure_celery function signature
from celery import Celery # <<< ADDED IMPORT

from peoples_coin.config import Config
from peoples_coin.extensions import db, migrate, cors, limiter, swagger, celery # Assuming 'celery' is an instance of Celery
from peoples_coin.routes.api import api_bp

def create_app(config_object=Config) -> Flask:
    """Creates and configures a new Flask application instance."""
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Setup logging, db, celery, extensions, and firebase
    setup_logging(app)
    init_extensions(app)
    init_firebase_admin(app)

    # Register components
    app.register_blueprint(api_bp)
    register_cli_commands(app)
    register_shutdown_handlers(app)

    logger = logging.getLogger(__name__)
    logger.info("✅ Application factory setup complete.")
    return app

def init_extensions(app: Flask):
    """Initialize all Flask extensions."""
    db.init_app(app)
    migrate.init_app(app, db)
    # --- CORS FIX ---
    # Explicitly allow your frontend's origin for production.
    # For local development, you might also need to add 'http://localhost:XXXX'
    # For example: origins=["https://brightacts.com", "http://localhost:3000"]
    cors.init_app(app, resources={r"/api/*": {"origins": "https://brightacts.com"}}) # <<< UPDATED LINE
    limiter.init_app(app)
    swagger.init_app(app)
    configure_celery(app, celery)

def configure_celery(app: Flask, celery_instance: Celery): # <<< Added Celery type hint
    """Configures Celery to run within the Flask application context."""
    celery_instance.conf.broker_url = app.config["CELERY_BROKER_URL"]
    celery_instance.conf.result_backend = app.config["CELERY_RESULT_BACKEND"]
    celery_instance.conf.update(app.config)

    class ContextTask(celery_instance.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_instance.Task = ContextTask
    app.extensions['celery'] = celery_instance

def setup_logging(app: Flask):
    """Configures logging for the application."""
    log_level = app.config["LOG_LEVEL"]
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
    path = app.config["FIREBASE_CREDENTIALS_PATH"]
    if not firebase_admin._apps:
        if os.path.exists(path):
            cred = credentials.Certificate(path)
            firebase_admin.initialize_app(cred)
            logging.getLogger(__name__).info("✅ Firebase Admin SDK initialized.")
        else:
            logging.getLogger(__name__).warning(f"⚠️ Firebase credentials not found at {path}. Auth may fail.")

def register_cli_commands(app: Flask):
    """Registers CLI commands for the application."""
    @app.cli.command("start-systems")
    def start_systems_command():
        """Starts the background systems (placeholder)."""
        click.echo("Starting background systems...")
        # from .extensions import immune_system, cognitive_system
        # immune_system.start()
        # cognitive_system.start()
        click.secho("✅ Systems would be running now.", fg="green")

def register_shutdown_handlers(app: Flask):
    """Registers graceful shutdown handlers."""
    def shutdown_systems(*args):
        logging.getLogger(__name__).warning("⚠️ Initiating graceful shutdown...")
        # from .extensions import immune_system, cognitive_system
        # immune_system.stop()
        # cognitive_system.stop()
        logging.getLogger(__name__).info("✅ Background systems shut down.")

    atexit.register(shutdown_systems)
    signal.signal(signal.SIGTERM, shutdown_systems)
    signal.signal(signal.SIGINT, shutdown_systems)

