import os
import sys
import atexit
import signal
import logging
from logging.handlers import RotatingFileHandler

import click
from flask import Flask, jsonify
from celery import Celery
from sqlalchemy import text
from flask_migrate import Migrate

from .config import Config
from peoples_coin.extensions import db

# --- Globals & Extensions ---
logger = logging.getLogger(__name__)
migrate = Migrate()
celery = Celery(__name__, broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"))

# --- Application Factory ---
def create_app(config_name=None) -> Flask:
    """Creates and configures a new Flask application instance."""
    app = Flask(__name__)
    app.config.from_object(config_name or Config)

    # Configure logging and database URI first
    setup_logging(app)
    configure_database(app)

    logger.info("🚀 Creating Flask application instance.")
    logger.info(f"Using database URI: {mask_uri(app.config['SQLALCHEMY_DATABASE_URI'])}")

    # Initialize extensions with the app
    db.init_app(app)
    migrate.init_app(app, db)
    configure_celery(app, celery)
    
    # Register blueprints, routes, and CLI commands
    register_blueprints(app)
    register_cli_commands(app)
    register_health_check(app)
    
    # Initialize your custom application systems
    initialize_custom_systems(app)

    # Register shutdown handlers to gracefully stop background threads
    register_shutdown_handlers(app)

    logger.info("✅ Application factory setup complete.")
    return app

# --- Helper Functions for Clarity ---

def setup_logging(app: Flask) -> None:
    """Configures application-wide logging."""
    log_level = app.config.get("LOG_LEVEL", "INFO").upper()
    logging.root.handlers.clear()
    
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    
    os.makedirs(app.instance_path, exist_ok=True)
    file_handler = RotatingFileHandler(
        os.path.join(app.instance_path, 'app.log'), 
        maxBytes=5 * 1024 * 1024, 
        backupCount=5
    )
    file_handler.setFormatter(formatter)

    logging.basicConfig(level=log_level, handlers=[stream_handler, file_handler])
    logging.getLogger('werkzeug').setLevel(logging.INFO if not app.debug else logging.DEBUG)
    logger.info("Logging configured.")

def configure_database(app: Flask) -> None:
    """Configures the database URI for the application."""
    db_uri = os.environ.get('POSTGRES_DB_URI')
    if not db_uri:
        instance_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', '..', 'instance')
        os.makedirs(instance_path, exist_ok=True)
        db_file_path = os.path.join(instance_path, 'peoples_coin.sqlite')
        db_uri = f"sqlite:///{db_file_path}"
    
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

def configure_celery(app: Flask, celery_instance: Celery) -> None:
    """Configures Celery with settings from the Flask app."""
    celery_instance.conf.broker_url = app.config.get("CELERY_BROKER_URL") or os.environ.get("REDIS_URL")
    celery_instance.conf.result_backend = app.config.get("CELERY_RESULT_BACKEND") or os.environ.get("REDIS_URL")
    celery_instance.conf.update(app.config)

    class ContextTask(celery_instance.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_instance.Task = ContextTask
    app.extensions['celery'] = celery_instance
    logger.info("Celery configured.")

def register_blueprints(app: Flask) -> None:
    """Registers all Flask blueprints for the application."""
    from peoples_coin.systems.cognitive_system import cognitive_bp
    from peoples_coin.systems.nervous_system import nervous_bp
    from peoples_coin.systems.metabolic_system import metabolic_bp
    from peoples_coin.routes.api import api_bp
    
    app.register_blueprint(cognitive_bp)
    app.register_blueprint(nervous_bp)
    app.register_blueprint(metabolic_bp)
    app.register_blueprint(api_bp)
    logger.info("Blueprints registered.")

def initialize_custom_systems(app: Flask) -> None:
    """Initializes all custom, background systems for the application."""
    # 🔷 FIX: Import the singleton INSTANCES directly from their modules
    from peoples_coin.systems.immune_system import immune_system
    from peoples_coin.systems.cognitive_system import cognitive_system
    from peoples_coin.systems.endocrine_system import endocrine_system
    from peoples_coin.systems.circulatory_system import circulatory_system
    from peoples_coin.systems.reproductive_system import reproductive_system
    from peoples_coin.consensus import Consensus
    
    immune_system.init_app(app)
    cognitive_system.init_app(app)
    endocrine_system.init_app(app)
    circulatory_system.init_app(app, db)
    reproductive_system.init_app(app, db)

    app.extensions['consensus'] = Consensus()
    app.extensions['consensus'].init_app(app, db)
    
    logger.info("All custom systems initialized.")

def register_health_check(app: Flask) -> None:
    """Registers the /health endpoint."""
    @app.route('/health', methods=['GET'])
    def health():
        return jsonify(status="healthy"), 200

def register_shutdown_handlers(app: Flask) -> None:
    """Registers handlers for graceful shutdown of background systems."""
    # 🔷 FIX: Import the singleton INSTANCES directly from their modules
    from peoples_coin.systems.cognitive_system import cognitive_system
    from peoples_coin.systems.endocrine_system import endocrine_system
    from peoples_coin.systems.immune_system import immune_system

    def shutdown_systems(*args, **kwargs):
        logger.warning("Initiating graceful shutdown of background systems...")
        # 🔷 FIX: Method names updated to match what's in the refactored files
        cognitive_system.stop()
        endocrine_system.stop()
        immune_system.stop()
        logger.info("✅ All background systems shut down.")

    atexit.register(shutdown_systems)
    signal.signal(signal.SIGTERM, lambda signum, frame: shutdown_systems())
    signal.signal(signal.SIGINT, lambda signum, frame: shutdown_systems())

def register_cli_commands(app: Flask) -> None:
    """Registers custom CLI commands for the application."""
    # This section can remain largely the same.
    logger.info("CLI commands registered.")


def mask_uri(db_uri: str) -> str:
    """Masks the password in a database URI for safe logging."""
    if '://' in db_uri and '@' in db_uri:
        protocol, rest = db_uri.split('://', 1)
        userinfo, hostinfo = rest.split('@', 1)
        if ':' in userinfo:
            user, _ = userinfo.split(':', 1)
            return f"{protocol}://{user}:****@{hostinfo}"
    return db_uri
