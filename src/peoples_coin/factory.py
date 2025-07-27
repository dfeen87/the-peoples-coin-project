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

    # Load configuration based on environment
    env = os.getenv("FLASK_ENV", "development")
    app.debug = (env != "production")

    if env == "production":
        app.config.from_object('peoples_coin.config.ProductionConfig')
    else:
        app.config.from_object('peoples_coin.config.DevelopmentConfig')

    # Setup CORS - read allowed origins from config, fallback to empty list
    cors_origins = app.config.get("CORS_ORIGINS", [])
    if not isinstance(cors_origins, (list, tuple)):
        cors_origins = [cors_origins]  # ensure list for flask_cors
    CORS(app, resources={r"/*": {"origins": cors_origins}}, supports_credentials=True)

    # Optional test route for debugging CORS
    @app.route("/test-cors")
    def test_cors():
        return jsonify({"msg": "CORS test successful"}), 200

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

    # Setup logging (file only in production)
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

    signal.signal(signal.SIGTERM, shutdown_handler)  # Cloud Run
    signal.signal(signal.SIGINT, shutdown_handler)   # Ctrl+C
    atexit.register(lambda: app.logger.info("🧹 Application exit cleanup done."))

    return app

