import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import atexit
import signal

from flask import Flask, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials

from .extensions import db, migrate, limiter
from .models import *
from .routes import register_routes


def create_app():
    app = Flask(__name__)

    # Load configuration from your config.py file
    # This part remains the same
    env = os.getenv("FLASK_ENV", "development")
    if env == "production":
        app.config.from_object('peoples_coin.config.Config') # Using the unified config
    else:
        app.config.from_object('peoples_coin.config.Config') # Using the unified config

    # --- THIS IS THE DIRECT FIX ---
    # We are bypassing the config files to be 100% sure.
    # This list explicitly tells the server which websites are allowed to connect.
    allowed_origins = [
        "https://brightacts.com",
        "https://peoples-coin-service-105378934751.us-central1.run.app",
        "http://localhost:5000",
        "http://localhost:8080"
        # Add any other specific local ports you see when running flutter
    ]
    # We apply CORS directly with our new, correct list.
    CORS(app, resources={r"/*": {"origins": allowed_origins}}, supports_credentials=True)
    # ------------------------------------

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    # Initialize Firebase Admin SDK if credentials provided
    firebase_cred_path = app.config.get("FIREBASE_CREDENTIAL_PATH")
    if firebase_cred_path and os.path.exists(firebase_cred_path) and not firebase_admin._apps:
        cred = credentials.Certificate(firebase_cred_path)
        firebase_admin.initialize_app(cred)
        app.logger.info("✅ Firebase initialized")
    else:
        app.logger.warning("⚠️ Firebase not initialized: Missing or invalid credential path")

    # Register all your blueprints/routes
    register_routes(app)

    # Setup logging
    if not app.debug:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        file_handler = RotatingFileHandler('logs/peoples_coin.log', maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

    app.logger.setLevel(logging.INFO)
    app.logger.info("🚀 People's Coin app startup complete")

    # Graceful shutdown handlers
    def shutdown_handler(signum, frame):
        app.logger.info(f"🛑 Received shutdown signal ({signal.Signals(signum).name}), exiting cleanly...")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    atexit.register(lambda: app.logger.info("🧹 Application exit cleanup done."))

    return app

