import os
import sys
import time
import atexit
import signal
import logging
import threading
from logging.handlers import RotatingFileHandler

import click
from flask import Flask, jsonify
from flask.cli import with_appcontext
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# --- Logging Setup ---
def setup_logging():
    logger = logging.getLogger()
    if logger.hasHandlers():
        return  # avoid duplicate handlers in dev
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logger.setLevel(log_level)

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File handler (rotating)
    if os.environ.get("LOG_FILE_ENABLED", "true").lower() == "true":
        log_file_path = os.environ.get("LOG_FILE_PATH", "app.log")
        fh = RotatingFileHandler(log_file_path, maxBytes=5*1024*1024, backupCount=5)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

setup_logging()
logger = logging.getLogger(__name__)

# --- Absolute imports ---
from peoples_coin.extensions import db
from peoples_coin.systems.endocrine_system import EndocrineSystem
from peoples_coin.systems.cognitive_system import register_cognitive_system, start_thought_loop, stop_thought_loop, _thought_loop_running
from peoples_coin.systems.immune_system import start_immune_system_cleaner, stop_immune_system_cleaner, _cleaner_thread
from peoples_coin.consensus import get_consensus_instance
from peoples_coin.systems.metabolic_system import metabolic_bp
from peoples_coin.systems.nervous_system import nervous_bp

ailee_controller = None
shutdown_event = threading.Event()

# --- App Factory ---
def create_app() -> Flask:
    logger.info("Creating main Flask application...")
    app = Flask(__name__, instance_path=os.path.abspath(os.path.join(os.getcwd(), 'instance')))
    os.makedirs(app.instance_path, exist_ok=True)

    db_uri = os.getenv('DATABASE_URL', f"sqlite:///{os.path.join(app.instance_path, 'peoples_coin.models')}")
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['DEBUG'] = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'

    logger.info(f"Database URI: {db_uri}")
    logger.info(f"Flask debug mode: {app.config['DEBUG']}")

    db.init_app(app)
    logger.info("Database initialized with Flask app.")

    with app.app_context():
        get_consensus_instance(app=app)

    # Register blueprints
    app.register_blueprint(metabolic_bp)
    app.register_blueprint(nervous_bp)
    register_cognitive_system(app)

    from peoples_coin.routes.auth import auth_bp
    from peoples_coin.routes.goodwill import goodwill_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(goodwill_bp)

    # CLI Commands
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
        try:
            db.session.execute('SELECT 1')
            click.echo("✅ Database OK")
        except Exception:
            click.echo("❌ Database not reachable")

        click.echo(f"{'✅' if ailee_controller and ailee_controller.is_running() else '⚠️'} AILEE running")
        click.echo(f"{'✅' if _thought_loop_running else '⚠️'} Cognitive loop running")
        click.echo(f"{'✅' if _cleaner_thread and _cleaner_thread.is_alive() else '⚠️'} Immune cleaner running")

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

    @app.route('/health', methods=['GET'])
    def health():
        try:
            db.session.execute('SELECT 1')
            return "OK", 200
        except Exception:
            return "DB Connection Error", 500

    return app

# --- Background Systems ---
def start_background_systems(app: Flask) -> None:
    logger.info("Starting all background systems...")
    global ailee_controller
    with app.app_context():
        try:
            start_immune_system_cleaner()
            start_thought_loop()
            ailee_controller = EndocrineSystem()
            ailee_controller.init_app(app)
            ailee_controller.start()
            logger.info("🚀 All core background systems launched.")
        except Exception as e:
            logger.error(f"Error starting background systems: {e}", exc_info=True)

def stop_all_background_systems() -> None:
    logger.info("Initiating graceful shutdown of background systems...")
    try:
        if ailee_controller:
            ailee_controller.stop()
        stop_thought_loop()
        stop_immune_system_cleaner()
        logger.info("✅ All background systems shut down successfully.")
    except Exception as e:
        logger.error(f"Error during shutdown of background systems: {e}", exc_info=True)

# --- Graceful SIGTERM & SIGINT Handler ---
def handle_exit_signal(*args) -> None:
    logger.info("Exit signal received. Shutting down gracefully.")
    shutdown_event.set()
    stop_all_background_systems()
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_exit_signal)
signal.signal(signal.SIGINT, handle_exit_signal)
atexit.register(stop_all_background_systems)

app = create_app()
start_background_systems(app)

# --- Main ---
if __name__ == '__main__':
    logger.info("Starting application in background service mode.")
    app = None
    try:
        app = create_app()
        start_background_systems(app)
        logger.info("--- SUCCESS: Application startup complete. Entering main loop. ---")

        while not shutdown_event.is_set():
            shutdown_event.wait(timeout=1)

    except Exception as e:
        logger.critical(f"An unexpected error occurred in the main process: {e}", exc_info=True)
    finally:
        stop_all_background_systems()
        logger.info("Main process finished.")

