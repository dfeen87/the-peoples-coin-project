import os
import sys
import atexit
import signal
import logging
from logging.handlers import RotatingFileHandler

import click
from flask import Flask, jsonify
from flask.cli import with_appcontext
from celery import Celery

from .config import Config
from .extensions import db, immune_system, cognitive_system, endocrine_system, circulatory_system
from .db.models import GoodwillAction, ChainBlock

logger = logging.getLogger(__name__)

def setup_logging(app):
    log_level = app.config.get("LOG_LEVEL", "INFO").upper()

    # Clear existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)

    log_dir = app.instance_path
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'app.log')
    fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5)
    fh.setFormatter(formatter)

    logging.basicConfig(level=log_level, handlers=[ch, fh])
    # Flask default werkzeug logger to INFO or DEBUG if debug mode
    logging.getLogger('werkzeug').setLevel(logging.INFO if not app.debug else logging.DEBUG)

def make_celery(app):
    celery = Celery(
        app.import_name,
        broker=app.config.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        backend=app.config.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    )
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Setup absolute path to DB file dynamically
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    instance_path = os.path.join(project_root, 'instance')
    os.makedirs(instance_path, exist_ok=True)
    db_file_path = os.path.join(instance_path, 'peoples_coin.db')

    # Support env var override for DATABASE_URL, else use local SQLite
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or f"sqlite:///{db_file_path}"

    setup_logging(app)
    logger.info("Creating Flask application instance.")

    # Initialize extensions & systems
    db.init_app(app)
    immune_system.init_app(app)
    cognitive_system.init_app(app)
    circulatory_system.init_app(app, db)
    endocrine_system.init_app(
        app,
        loop_delay=app.config.get("AILEE_LOOP_DELAY", 5),
        max_workers=app.config.get("AILEE_MAX_WORKERS", 2)
    )

    logger.info("All systems initialized.")

    # Register blueprints
    from .systems.nervous_system import nervous_bp
    from .systems.metabolic_system import metabolic_bp
    from .systems.cognitive_system import cognitive_bp
    from .routes.api import api_bp

    app.register_blueprint(nervous_bp)
    app.register_blueprint(metabolic_bp)
    app.register_blueprint(cognitive_bp)
    app.register_blueprint(api_bp)

    logger.info("All blueprints registered.")

    # Initialize consensus system
    from .consensus import Consensus
    consensus = Consensus()
    consensus.init_app(app, db)
    logger.info("Consensus system initialized.")

    # Setup Celery and attach for global access
    celery = make_celery(app)
    app.extensions['celery'] = celery
    logger.info("Celery initialized and attached to app.extensions.")

    @app.route('/health', methods=['GET'])
    def health():
        return jsonify(status="healthy"), 200

    register_cli_commands(app, consensus)

    def shutdown_systems(*args):
        logger.info("Initiating graceful shutdown of background systems...")
        cognitive_system.stop_background_loop()
        endocrine_system.stop()
        immune_system.stop_cleaner()  # Assuming this is the correct stop method
        logger.info("✅ All background systems shut down successfully.")

    atexit.register(shutdown_systems)
    signal.signal(signal.SIGTERM, lambda *args: shutdown_systems() or sys.exit(0))
    signal.signal(signal.SIGINT, lambda *args: shutdown_systems() or sys.exit(0))

    logger.info("🚀 Application factory setup complete.")
    return app

def register_cli_commands(app: Flask, consensus: 'Consensus'):
    @app.cli.command('init-db')
    @click.option('--drop', is_flag=True, help="Drop database file. Use 'alembic upgrade head' to create tables.")
    def init_db_command(drop):
        with app.app_context():
            db_uri = app.config.get('SQLALCHEMY_DATABASE_URI')
            logger.info(f"Preparing database at: {db_uri}")

            db_path = None
            if db_uri and db_uri.startswith('sqlite:///'):
                db_path = db_uri.replace('sqlite:///', '')

            if db_path:
                db_dir = os.path.dirname(db_path)
                try:
                    os.makedirs(db_dir, exist_ok=True)
                    logger.info(f"Ensured database directory exists: {db_dir}")
                except Exception as e:
                    logger.error(f"Failed to create DB directory {db_dir}: {e}", exc_info=True)
                    click.secho(f"❌ Error creating DB directory: {e}", fg='red')
                    sys.exit(1)

            if drop:
                click.echo('⚠️  Dropping database file...')
                if db_path and os.path.exists(db_path):
                    try:
                        db.session.remove()
                        if db.engine:
                            db.engine.dispose()
                            logger.debug("Disposed SQLAlchemy engine to release DB file lock.")
                        os.remove(db_path)
                        logger.warning(f"Deleted existing DB file: {db_path}")
                    except Exception as e:
                        logger.error(f"Failed to delete DB file {db_path}: {e}", exc_info=True)
                        click.secho(f"❌ Error deleting DB file: {e}", fg='red')
                        sys.exit(1)
                else:
                    logger.info(f"No DB file found at {db_path} to delete.")
                click.echo('Database file cleared. Run "alembic upgrade head" to create tables.')
            else:
                click.echo('Database preparation complete. Run "alembic upgrade head" to create/update tables.')

            click.echo('✅ Database preparation command finished.')

    @app.cli.command('create-genesis-block')
    def create_genesis_block_command():
        with app.app_context():
            try:
                consensus._create_genesis_block_if_needed()
                click.secho("✅ Genesis block creation checked/completed.", fg='green')
            except Exception as e:
                click.secho(f"❌ Failed to create genesis block: {e}", fg='red')
                logger.error(f"Error creating genesis block: {e}", exc_info=True)
                sys.exit(1)

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


