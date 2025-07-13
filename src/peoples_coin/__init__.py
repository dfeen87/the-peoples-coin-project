import os
import sys
import atexit
import signal
import logging
from logging.handlers import RotatingFileHandler

import click
from flask import Flask, jsonify
from flask.cli import with_appcontext

# --- Import System Components ---
from .config import Config # Assume a config.py file exists
from .db import db
from .db.models import GoodwillAction # Import the model for the new command
from .systems.immune_system import ImmuneSystem
from .systems.cognitive_system import CognitiveSystem, cognitive_bp
from .systems.endocrine_system import EndocrineSystem
from .systems.circulatory_system import CirculatorySystem
from .systems.consensus import Consensus
from .systems.nervous_system import nervous_bp
from .systems.metabolic_system import metabolic_bp

# --- Instantiate Global System Objects ---
immune_system = ImmuneSystem()
cognitive_system = CognitiveSystem()
endocrine_system = EndocrineSystem()
circulatory_system = CirculatorySystem()
consensus = Consensus()

def setup_logging(app):
    """Configures application-wide logging."""
    log_level = app.config.get("LOG_LEVEL", "INFO").upper()
    # Remove default handlers to avoid duplicates
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    # Console Handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    # File Handler
    fh = RotatingFileHandler('app.log', maxBytes=5*1024*1024, backupCount=5)
    fh.setFormatter(formatter)
    
    logging.basicConfig(level=log_level, handlers=[ch, fh])
    logging.getLogger('werkzeug').setLevel(logging.INFO if not app.debug else logging.DEBUG)


def create_app(config_class=Config):
    """
    The main application factory. Creates and configures the Flask app
    and all associated systems.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # --- Initialize Logging and Systems in Order ---
    setup_logging(app)
    logger = logging.getLogger(__name__)
    logger.info("Creating main Flask application...")

    db.init_app(app)
    immune_system.init_app(app)
    cognitive_system.init_app(app)
    circulatory_system.init_app(app, db)
    consensus.init_app(app, db)
    
    with app.app_context():
        endocrine_system.init_app(app, max_workers=app.config.get("AILEE_MAX_WORKERS", 2))
    
    logger.info("All systems initialized.")

    # --- Register Blueprints ---
    app.register_blueprint(nervous_bp)
    app.register_blueprint(metabolic_bp)
    app.register_blueprint(cognitive_bp)
    logger.info("All blueprints registered.")

    # --- Register Custom CLI Commands ---
    register_cli_commands(app)

    # --- Register Graceful Shutdown Hooks ---
    def shutdown_systems():
        logger.info("Initiating graceful shutdown of background systems...")
        cognitive_system.stop_background_loop()
        endocrine_system.stop()
        logger.info("✅ All background systems shut down successfully.")

    atexit.register(shutdown_systems)
    signal.signal(signal.SIGTERM, lambda *args: shutdown_systems() or sys.exit(0))
    
    logger.info("🚀 Application startup complete.")
    return app


def register_cli_commands(app: Flask):
    """A dedicated function to register all custom CLI commands."""

    @app.cli.command('init-db')
    @click.option('--drop', is_flag=True, help="Drop all tables before creating them.")
    def init_db_command(drop):
        with app.app_context():
            if drop:
                click.echo('⚠️  Dropping all database tables...')
                db.drop_all()
            click.echo('Initializing database schema...')
            db.create_all()
            consensus._create_genesis_block_if_needed()
            click.echo('✅ Database initialized successfully.')

    @app.cli.command('healthcheck')
    def healthcheck_command():
        """Checks the health of the database and background systems."""
        with app.app_context():
            try:
                db.session.execute('SELECT 1')
                click.secho("✅ Database OK", fg='green')
            except Exception as e:
                click.secho(f"❌ Database not reachable: {e}", fg='red')
            
            click.echo(f"  - Endocrine System (AILEE): {'✅ Running' if endocrine_system.is_running() else '⚠️ Stopped'}")
            click.echo(f"  - Cognitive System Loop:  {'✅ Running' if cognitive_system.is_running() else '⚠️ Stopped'}")
            click.echo(f"  - Immune System Cleaner:  {'✅ Running' if immune_system.is_cleaner_running() else '⚠️ Stopped'}")

    @app.cli.command('check-goodwill')
    @click.option('--limit', default=20, help='Number of records to fetch.')
    @click.option('--status', default=None, help="Filter by status (e.g., 'pending', 'completed').")
    def check_goodwill_command(limit, status):
        """Inspects GoodwillAction records in the database."""
        with app.app_context():
            query = db.session.query(GoodwillAction)
            if status:
                query = query.filter_by(status=status)
            
            actions = query.order_by(GoodwillAction.id.desc()).limit(limit).all()
            
            if not actions:
                click.secho("❌ No GoodwillAction records found matching the criteria.", fg='yellow')
                return

            click.secho(f"--- Showing last {len(actions)} Goodwill Actions ---", bold=True)
            for action in actions:
                status_color = 'green' if action.status == 'completed' else 'yellow'
                click.echo(
                    f"✅ ID: {click.style(str(action.id), bold=True)} | "
                    f"User: {action.user_id} | "
                    f"Status: {click.style(action.status, fg=status_color)} | "
                    f"Minted: {action.minted_token_id or 'No'}"
                )

