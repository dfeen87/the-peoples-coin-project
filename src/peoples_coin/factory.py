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
# Import the corrected register_routes function
from .routes import register_routes


def create_app():
    app = Flask(__name__)

    # Load configuration
    app.config.from_object('peoples_coin.config.Config')

    # --- Hardcoded CORS Fix ---
    allowed_origins = [
        "https://brightacts.com",
        "https://peoples-coin-service-105378934751.us-central1.run.app",
        "http://localhost:5000",
        "http://localhost:8080"
    ]
    CORS(app, resources={r"/*": {"origins": allowed_origins}}, supports_credentials=True)
    # ------------------------------------

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    # Initialize Firebase Admin SDK
    firebase_cred_path = app.config.get("FIREBASE_CREDENTIAL_PATH")
    if firebase_cred_path and os.path.exists(firebase_cred_path) and not firebase_admin._apps:
        cred = credentials.Certificate(firebase_cred_path)
        firebase_admin.initialize_app(cred)
        app.logger.info("✅ Firebase initialized")
    else:
        app.logger.warning("⚠️ Firebase not initialized: Missing or invalid credential path")

    # --- Simplified Route Registration ---
    # This single line now handles all your routes.
    register_routes(app)

    # Setup logging
    # ... (logging and shutdown handler code remains the same)

    app.logger.setLevel(logging.INFO)
    app.logger.info("🚀 People's Coin app startup complete")

    def shutdown_handler(signum, frame):
        app.logger.info(f"🛑 Received shutdown signal ({signal.Signals(signum).name}), exiting cleanly...")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    atexit.register(lambda: app.logger.info("🧹 Application exit cleanup done."))

    return app

