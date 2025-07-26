import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import signal
import atexit

from flask import Flask, jsonify

from dotenv import load_dotenv
load_dotenv()

# SQLAlchemy
from peoples_coin.db import db

# Celery setup (optional)
from peoples_coin.tasks import make_celery

# Blueprints (example)
from peoples_coin.routes import api_blueprint  # adjust as needed

# Firebase (optional)
try:
    import firebase_admin
    from firebase_admin import credentials
except ImportError:
    firebase_admin = None


def create_app():
    app = Flask(__name__)

    # Config selection
    env = os.getenv("FLASK_ENV", "development")
    if env == "production":
        app.config.from_object("peoples_coin.config.ProductionConfig")
    else:
        app.config.from_object("peoples_coin.config.DevelopmentConfig")

    # Logging
    setup_logging(app)

    # Firebase (optional)
    if firebase_admin and not firebase_admin._apps:
        cred_path = os.getenv("FIREBASE_CREDENTIAL_PATH")
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            app.logger.info("✅ Firebase initialized")
        else:
            app.logger.warning("⚠️ Firebase not initialized: Credential path not found")

    # Healthcheck route for Cloud Run startup probe
    @app.route('/healthz_root')
    def healthz():
        return jsonify(status="healthy"), 200

    # Register blueprints
    app.register_blueprint(api_blueprint)

    # Initialize database
    db.init_app(app)

    # Initialize Celery
    celery = make_celery(app)
    app.celery = celery

    # Graceful shutdown
    def shutdown_handler(signum, frame):
        app.logger.info(f"🛑 Received shutdown signal ({signum}), cleaning up...")

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    atexit.register(lambda: app.logger.info("🧹 Application shutting down..."))

    return app


def setup_logging(app):
    log_dir = os.path.join(os.getcwd(), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'peoples_coin.log'),
        maxBytes=10240,
        backupCount=10
    )
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    app.logger.addHandler(file_handler)
    app.logger.addHandler(stream_handler)
    app.logger.setLevel(logging.INFO)

    app.logger.info("📋 Logging is set up.")

