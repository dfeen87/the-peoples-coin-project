import os
import sys
import atexit
import signal
import logging
from logging.handlers import RotatingFileHandler

import click
from flask import Flask
from flask.cli import with_appcontext

from .config import Config
from .extensions import db, immune_system, cognitive_system, endocrine_system, circulatory_system, consensus
from .db.models import GoodwillAction

def setup_logging(app):
    log_level = app.config.get("LOG_LEVEL", "INFO").upper()
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    log_file = os.path.join(app.instance_path, 'app.log')
    fh = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5)
    fh.setFormatter(formatter)
    logging.basicConfig(level=log_level, handlers=[ch, fh])
    logging.getLogger('werkzeug').setLevel(logging.INFO if not app.debug else logging.DEBUG)

def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    setup_logging(app)
    logger = logging.getLogger(__name__)
    logger.info("Creating Flask application instance.")

    db.init_app(app)
    immune_system.init_app(app)
    cognitive_system.init_app(app)
    circulatory_system.init_app(app, db)
    consensus.init_app(app, db)
    endocrine_system.init_app(app, max_workers=app.config.get("AILEE_MAX_WORKERS", 2))
    
    logger.info("All systems initialized.")

    from .systems.nervous_system import nervous_bp
    from .systems.metabolic_system import metabolic_bp
    from .systems.cognitive_system import cognitive_bp
    
    app.register_blueprint(nervous_bp)
    app.register_blueprint(metabolic_bp)
    app.register_blueprint(cognitive_bp)
    logger.info("All blueprints registered.")

    register_cli_commands(app)

    def shutdown_systems():
        logger.info("Initiating graceful shutdown of background systems...")
        cognitive_system.stop_background_loop()
        endocrine_system.stop()
        logger.info("✅ All background systems shut down successfully.")

    atexit.register(shutdown_systems)
    signal.signal(signal.SIGTERM, lambda *args: shutdown_systems() or sys.exit(0))
    
    logger.info("🚀 Application factory setup complete.")
    return app

def register_cli_commands(app: Flask):
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
        with app.app_context():
            try:
                db.session.execute(db.text('SELECT 1'))
                click.secho("✅ Database OK", fg='green')
            except Exception as e:
                click.secho(f"❌ Database not reachable: {e}", fg='red')
            
            click.echo(f"  - Endocrine System: {'✅ Running' if endocrine_system.is_running() else '⚠️ Stopped'}")
            click.echo(f"  - Cognitive System: {'✅ Running' if cognitive_system.is_running() else '⚠️ Stopped'}")
            click.echo(f"  - Immune System:    {'✅ Running' if immune_system.is_cleaner_running() else '⚠️ Stopped'}")

