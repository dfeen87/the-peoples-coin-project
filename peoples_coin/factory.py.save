import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import signal
import atexit

# Third-party imports
from flask import Flask, jsonify
from flask_cors import CORS # <-- Import CORS
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Local application imports
from peoples_coin.models.db import db
from peoples_coin.routes import api_blueprint
from peoples_coin.celery_app import make_celery

# Optional Firebase import
try:
    import firebase_admin
    from firebase_admin import credentials
except ImportError:
    firebase_admin = None


def create_app():
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__)

    # 1. Load Configuration
    env = os.getenv("FLASK_ENV", "development")
    if env == "production":
        app.config.from_object("peoples_coin.config.ProductionConfig")
    else:
        app.config.from_object("peoples_coin.config.DevelopmentConfig")

    # 2. Setup Logging
    setup_logging(app, env)
    
    # 3. Initialize Extensions
    db.init_app(app)
    
    # Initialize Celery and attach to app context
    celery = make_celery(app)
    app.celery = celery
    
    # 5. Initialize Firebase (if available)
    if firebase_admin and not firebase_admin._apps:
        cred_path = os.getenv("FIREBASE_CREDENTIAL_PATH")
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            app.logger.info("✅ Firebase initialized")
        else:
            app.logger.warning(
                "⚠️ Firebase not initialized: Credential path missing or invalid."
            )
            
    # 6. Register Blueprints
    app.register_blueprint(api_blueprint)

    # 7. Add Health Check Route
    @app.route('/healthz')
    def healthz():
        """Health check endpoint for Cloud Run/Kubernetes probes."""
        return jsonify(status="healthy"), 200

    # 8. Register Shutdown Handlers
    setup_shutdown_handlers(app)

    return app


def setup_logging(app, env):
    """Configures logging for the application."""
    # Clear existing handlers to prevent duplicate logs
    if app.logger.hasHandlers():
        app.logger.handlers.clear()

    # Use stdout for logs in all environments, which is standard for containers
    stream_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )
    stream_handler.setFormatter(formatter)
    app.logger.addHandler(stream_handler)

    # Add file logging only for local development
    if env == 'development':
        log_dir = os.path.join(os.getcwd(), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, 'peoples_coin_dev.log'),
            maxBytes=10240,
            backupCount=10
        )
        file_handler.setFormatter(formatter)
        app.logger.addHandler(file_handler)

    app.logger.setLevel(logging.INFO)
    app.logger.info("📋 Logging is set up.")


def setup_shutdown_handlers(app):
    """Sets up graceful shutdown signal handlers."""
    def shutdown_handler(signum, frame):
        app.logger.info(f"🛑 Received shutdown signal ({signal.Signals(signum).name}), cleaning up...")
        # Add any specific cleanup logic here (e.g., closing connections)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler) # Sent by Cloud Run
    signal.signal(signal.SIGINT, shutdown_handler)  # Sent by Ctrl+C
    atexit.register(lambda: app.logger.info("🧹 Application exiting."))
