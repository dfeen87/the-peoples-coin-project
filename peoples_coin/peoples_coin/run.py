import os
import sys
import time
import atexit
import logging
from logging.handlers import RotatingFileHandler

import click
from flask import Flask, current_app
from flask.cli import with_appcontext
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # Rotating file handler: 5 MB per file, keep 5 backups
    fh = RotatingFileHandler('app.log', maxBytes=5*1024*1024, backupCount=5)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

# Setup logging as early as possible
setup_logging()
logger = logging.getLogger(__name__)

from .db import db
from .systems.endocrine_system import AILEEController
from .systems.cognitive_system import register_cognitive_system, start_thought_loop, stop_thought_loop
from .systems.immune_system import start_immune_system_cleaner, stop_immune_system_cleaner
from .consensus import get_consensus_instance
from .systems.metabolic_system import metabolic_bp
from .systems.nervous_system import nervous_bp


def create_app():
    """The main application factory. Creates and configures the Flask app."""
    logger.info("Creating main Flask application...")
    app = Flask(__name__, instance_path=os.path.abspath(os.path.join(os.getcwd(), 'instance')))
    
    os.makedirs(app.instance_path, exist_ok=True)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', f"sqlite:///{os.path.join(app.instance_path, 'peoples_coin.db')}")
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    logger.info("Database initialized with Flask app.")
    
    with app.app_context():
        get_consensus_instance(app=app)

    app.register_blueprint(metabolic_bp)
    app.register_blueprint(nervous_bp)
    
    # Registers cognitive system blueprint and teardown
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

    return app


ailee_controller = None


def start_background_systems(app):
    """Initializes and starts all core background processing systems in the correct order."""
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
    logger.info("Initiating graceful shutdown...")
    if ailee_controller:
        ailee_controller.stop()
    stop_thought_loop()
    stop_immune_system_cleaner()
    logger.info("✅ All background systems shut down.")


atexit.register(stop_all_background_systems)


if __name__ == '__main__':
    """Main entry point for running background services."""
    logger.info("Starting application in background service mode.")
    try:
        app = create_app()
        start_background_systems(app)
        logger.info("--- SUCCESS: Application startup complete. Entering main loop. ---")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected. Shutting down...")
    except Exception as e:
        logger.critical(f"An unexpected error occurred in the main process: {e}", exc_info=True)
    finally:
        logger.info("Main process finished.")

