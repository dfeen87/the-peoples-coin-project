import os
import sys
import time
import atexit
import signal
import logging
from logging.handlers import RotatingFileHandler

import click
from flask import Flask, jsonify
from flask.cli import with_appcontext
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# --- Logging Setup ---
def setup_logging():
    logger = logging.getLogger()
    if logger.hasHandlers():
        return  # avoid duplicate handlers in dev
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # Rotating file
    fh = RotatingFileHandler('app.log', maxBytes=5*1024*1024, backupCount=5)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

setup_logging()
logger = logging.getLogger(__name__)


# --- Imports that require logging set up ---
from .db import db
from .systems.endocrine_system import AILEEController
from .systems.cognitive_system import register_cognitive_system, start_thought_loop, stop_thought_loop, _thought_loop_running
from .systems.immune_system import start_immune_system_cleaner, stop_immune_system_cleaner, _cleaner_thread
from .consensus import get_consensus_instance
from .systems.metabolic_system import metabolic_bp
from .systems.nervous_system import nervous_bp


ailee_controller = None


# --- App Factory ---
def create_app():
    """Create and configure the Flask app."""
    logger.info("Creating main Flask application...")
    app = Flask(__name__, instance_path=os.path.abspath(os.path.join(os.getcwd(), 'instance')))
    os.makedirs(app.instance_path, exist_ok=True)

    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', f"sqlite:///{os.path.join(app.instance_path, 'peoples_coin.db')}")
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    logger.info("Database initialized with Flask app.")

    with app.app_context():
        get_consensus_instance(app=app)

    # Register blueprints
    app.register_blueprint(metabolic_bp)
    app.register_blueprint(nervous_bp)
    register_cognitive_system(app)

    @app.cli.command('init-db')
    @click.option('--drop', is_flag=True, help="Drop all tables before creating them.")
    @with_appcontext
    def init_db_command(drop):
        if drop:
            click.echo('⚠️  Dropping all database tables...')
            db.drop_all()
        click.echo('Initializing database schema...')
        db.create_all()
        click.echo('✅ Database initialized successfully.')

    @app.cli.command('healthcheck')
    @with_appcontext
    def healthcheck():
        """Check health of database & background systems."""
        try:
            db.session.execute('SELECT 1')
            click.echo("✅ Database OK")
        except Exception:
            click.echo("❌ Database not reachable")
        if ailee_controller and ailee_controller.is_running():
            click.echo("✅ AILEE running")
        else:
            click.echo("⚠️ AILEE not running")
        if _thought_loop_running:
            click.echo("✅ Cognitive loop running")
        else:
            click.echo("⚠️ Cognitive loop not running")
        if _cleaner_thread and _cleaner_thread.is_alive():
            click.echo("✅ Immune cleaner running")
        else:
            click.echo("⚠️ Immune cleaner not running")

    # App-level status route
    @app.route('/status', methods=['GET'])
    def app_status():
        try:
            db.session.execute('SELECT 1')
            db_status = "✅"
        except Exception:
            db_status = "❌"
        return jsonify({
            "app": "running",
            "database": db_status,
            "cognitive_loop": _thought_loop_running,
            "ailee": ailee_controller.is_running() if ailee_controller else False,
            "immune_cleaner": _cleaner_thread.is_alive() if _cleaner_thread else False
        })

    return app


# --- Background Systems ---
def start_background_systems(app):
    """Start all core background processing systems in correct order."""
    logger.info("Starting all background systems...")
    global ailee_controller
    with app.app_context():
        start_immune_system_cleaner()
        start_thought_loop()
        ailee_controller = AILEEController.get_instance(app=app, db=db)
        ailee_controller.start()
    logger.info("🚀 All core background systems launched.")


def stop_all_background_systems():
    """Graceful shutdown for all background systems."""
    logger.info("Initiating graceful shutdown of background systems...")
    try:
        if ailee_controller:
            ailee_controller.stop()
        stop_thought_loop()
        stop_immune_system_cleaner()
        logger.info("✅ All background systems shut down successfully.")
    except Exception as e:
        logger.error(f"Error during shutdown of background systems: {e}", exc_info=True)


# --- Graceful SIGTERM Handler ---
def handle_sigterm(*args):
    logger.info("SIGTERM received. Shutting down gracefully.")
    stop_all_background_systems()
    sys.exit(0)


signal.signal(signal.SIGTERM, handle_sigterm)
atexit.register(stop_all_background_systems)


# --- Main ---
if __name__ == '__main__':
    """Main entry point for running background services."""
    logger.info("Starting application in background service mode.")
    app = None
    try:
        app = create_app()
        start_background_systems(app)
        logger.info("--- SUCCESS: Application startup complete. Entering main loop. ---")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected. Shutting down gracefully...")
    except Exception as e:
        logger.critical(f"An unexpected error occurred in the main process: {e}", exc_info=True)
    finally:
        stop_all_background_systems()
        logger.info("Main process finished.")

