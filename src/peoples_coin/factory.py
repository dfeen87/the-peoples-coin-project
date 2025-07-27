import os
import sys
print("!!! FACTORY.PY IS BEING EXECUTED (UNBUFFERED) !!!", file=sys.stderr, flush=True)

import logging
from logging.handlers import RotatingFileHandler
import atexit
import signal

import click
from flask import Flask, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials

from .extensions import db
from .models import *
from .routes import register_routes


def create_app():
    app = Flask(__name__)

    # Load configuration
    app.config.from_object('config.Config')

    # Enable CORS
    CORS(app, resources={r"/*": {"origins": "*"}})

    # Register test route for debugging CORS
    @app.route("/test-cors")
    def test_cors():
        return jsonify({"msg": "CORS test successful"}), 200, {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization'
        }

    # Register routes/blueprints
    register_routes(app)

    # Initialize extensions
    db.init_app(app)

    # Firebase Admin SDK setup
    firebase_cred_path = app.config.get("FIREBASE_CREDENTIALS")
    if firebase_cred_path and not firebase_admin._apps:
        cred = credentials.Certificate(firebase_cred_path)
        firebase_admin.initialize_app(cred)

    # Logging
    if not app.debug:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        file_handler = RotatingFileHandler('logs/peoples_coin.log', maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

        app.logger.setLevel(logging.INFO)
        app.logger.info('People\'s Coin startup')

    # Graceful shutdown
    def shutdown_handler(signum, frame):
        print("Shutting down gracefully...")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    atexit.register(lambda: print("Exited cleanly."))

    return app


@click.command()
@click.option('--host', default='0.0.0.0')
@click.option('--port', default=5000)
def run(host, port):
    app = create_app()
    app.run(host=host, port=port)


if __name__ == "__main__":
    run()

