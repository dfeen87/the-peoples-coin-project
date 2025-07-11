import os
import logging
from datetime import datetime, timezone, timedelta
import time
import threading

from flask import Flask, jsonify, request, current_app
from flask.cli import with_appcontext
import click

from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import systems
from peoples_coin.peoples_coin.db.db import db
from peoples_coin.peoples_coin.db.models import DataEntry, GoodwillAction
from peoples_coin.peoples_coin.systems.endocrine_system import AILEEController
from peoples_coin.peoples_coin.systems.nervous_system import create_nervous_app
from peoples_coin.peoples_coin.systems.skeleton_system import create_skeleton_app
from peoples_coin.peoples_coin.systems.metabolic_system import metabolic_bp
from peoples_coin.peoples_coin.systems.cognitive_system import register_cognitive_system, stop_thought_loop
from peoples_coin.peoples_coin.systems.immune_system import register_immune_system_shutdown, stop_immune_system_cleaner

def create_app():
    app = Flask(__name__, instance_path=os.path.abspath(os.path.join(os.getcwd(), 'instance')))
    
    # Ensure instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)
    logger.info(f"Instance directory already exists: {app.instance_path}")

    # Database configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(app.instance_path, 'peoples_coin.db')}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # Register blueprints for the main app
    app.register_blueprint(metabolic_bp)
    # Nervous and Skeleton Systems are separate Flask apps, not blueprints for the main app.
    # Their blueprints are handled within their own `create_app` functions.

    # Initialize AILEEController instance within the app context
    # This context is pushed by Flask when it runs the 'create_app' function
    # during `flask run` or `python -m flask run` CLI commands.
    with app.app_context():
        global ailee_controller
        ailee_controller = AILEEController.get_instance(app=app, db=db, loop_delay=5, max_workers=2)
        logger.info("AILEEController initialized within Flask app context (via create_app).")

        # Instantiate Nervous System's Flask app using its factory function
        global nervous_system_instance
        nervous_system_instance = create_nervous_app() # Call the factory to get the app instance

        # Instantiate Skeleton System's Flask app using its factory function
        global skeleton_system_instance
        skeleton_system_instance = create_skeleton_app() # Call the factory to get the app instance

        # Register Cognitive System's blueprint and start its thought loop
        register_cognitive_system(app) # This will register the blueprint AND start the thought loop
        logger.info("🧠 Cognitive system blueprint registered and thought loop launched.")

        # Register Immune System's shutdown handler and start its cleaner thread
        register_immune_system_shutdown(app) # This will start the cleaner and register the shutdown hook
        logger.info("🛡️ Immune System cleaner thread launched and shutdown hook registered.")


    # CLI commands for database
    @app.cli.command('init-db')
    @with_appcontext
    def init_db_command():
        """Clear existing data and create new tables."""
        init_db()
        click.echo('Initialized the database.')

    @app.cli.command('test-db')
    @with_appcontext
    def test_db_command():
        """Test database connection."""
        test_db_connection()
        click.echo('Database connection tested.')

    @app.cli.command('populate-test-data')
    @with_appcontext
    def populate_test_data_command():
        """Populate database with test data."""
        populate_test_data()
        click.echo('Populated test data.')

    @app.cli.command('start-background-systems')
    @with_appcontext
    def start_background_systems_command():
        """Starts AILEE, Immune, Nervous, Skeleton, and Cognitive systems."""
        # This function is now called within the app context by the CLI decorator,
        # so `current_app` will be available if needed inside.
        start_ailee_and_other_systems()
        click.echo('Background systems started.')
        # Keep the main thread alive for background systems
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            click.echo('Shutting down background systems...')
            stop_ailee_and_other_systems()
            click.echo('Background systems shut down.')

    return app

def init_db():
    logger.info("Entering init_db function.")
    # current_app is available here because this function is called via a CLI command with @with_appcontext
    # or explicitly from __main__ with app.app_context()
    db_path = os.path.join(current_app.instance_path, 'peoples_coin.db')
    logger.info(f"Database file 'peoples_coin.db' exists before create_all(): {os.path.exists(db_path)}")
    
    db.create_all()
    logger.info("Attempted to create/verify database tables.")
    
    logger.info(f"Database file 'peoples_coin.db' exists after create_all(): {os.path.exists(db_path)}")

    try:
        dummy_action = GoodwillAction(
            user_id="dummy",
            action_type="test",
            description="dummy",
            timestamp=datetime.now(timezone.utc),
            status="test"
        )
        db.session.add(dummy_action)
        db.session.commit()
        db.session.delete(dummy_action)
        db.session.commit()
        logger.info("Schema verification: Successfully inserted and deleted dummy GoodwillAction. 'status' column and others are present.")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Schema verification failed: {e}", exc_info=True)
        raise RuntimeError(f"Database schema verification failed: {e}")

    logger.info("✅ Database tables ensured (via db.create_all()).")

def test_db_connection():
    logger.info("Entering test_db_connection function.")
    # current_app is available here
    try:
        db.session.query(DataEntry).first()
        logger.info("✅ Database connection verified.")
    except Exception as e:
        logger.error(f"Database connection failed: {e}", exc_info=True)
        raise RuntimeError(f"Database connection failed: {e}")

def populate_test_data():
    logger.info("Entering populate_test_data function.")
    # current_app is available here
    if db.session.query(DataEntry).count() == 0:
        logger.info("No existing entries found. Populating test data...")
        test_entries = [
            # FIX: Changed 'timestamp' to 'created_at' for DataEntry
            DataEntry(value="test_data_1", created_at=datetime.now(timezone.utc)),
            DataEntry(value="test_data_2", created_at=datetime.now(timezone.utc)),
            DataEntry(value="test_data_3", created_at=datetime.now(timezone.utc))
        ]
        db.session.bulk_save_objects(test_entries)
        db.session.commit()
        logger.info("✅ Populated 3 test DataEntry items.")

        initial_goodwill_actions = [
            GoodwillAction(
                user_id="initial_user_1",
                action_type="community_support",
                description="Organized a local park cleanup.",
                timestamp=datetime.now(timezone.utc) - timedelta(days=1),
                status='pending'
            ),
            GoodwillAction(
                user_id="initial_user_2",
                action_type="environmental_contribution",
                description="Planted 50 trees in the local forest.",
                timestamp=datetime.now(timezone.utc) - timedelta(hours=12),
                status='pending'
            )
        ]
        db.session.bulk_save_objects(initial_goodwill_actions)
        db.session.commit()
        logger.info("✅ Populated 2 initial GoodwillAction items with 'pending' status.")

    else:
        logger.info(f"✅ Found {db.session.query(DataEntry).count()} existing entries. Skipping test data.")

background_systems_thread = None
nervous_system_thread = None
skeleton_system_thread = None
cognitive_system_thread = None
immune_system_thread = None

def start_ailee_and_other_systems():
    logger.info("Entering start_ailee_and_other_systems function.")
    # This function is now always called within an app context (either from CLI or from __main__ block)
    # So `current_app` is fine to use here.
    
    # Start AILEE Controller
    logger.info("Attempting to call ailee_controller.start().")
    ailee_controller.start()
    logger.info(f"🧠 AILEEController started with {ailee_controller.max_workers} workers and {ailee_controller.loop_delay}s loop delay.")
    
    worker_status = ailee_controller.status().get("worker_threads_alive", [])
    logger.info(f"AILEEController: Confirmed {len(worker_status)} worker threads are initialized.")
    for i, status in enumerate(worker_status):
        logger.info(f"AILEEController: Worker thread {i+1} (AILEEWorker-{i+1}) status: alive={status}")


    logger.info("Attempting to start Nervous and Skeleton Systems.")
    # Start Nervous System (as a separate Flask app in its own thread)
    def run_nervous_system():
        nervous_system_instance.run(port=5001, use_reloader=False, debug=False)
    
    global nervous_system_thread
    nervous_system_thread = threading.Thread(target=run_nervous_system, daemon=True)
    nervous_system_thread.start()
    logger.info("🚀 Starting Nervous System on port 5001...")

    # Start Skeleton System (as a separate Flask app in its own thread)
    def run_skeleton_system():
        skeleton_system_instance.run(port=5002, use_reloader=False, debug=False)

    global skeleton_system_thread
    skeleton_system_thread = threading.Thread(target=run_skeleton_system, daemon=True)
    skeleton_system_thread.start()
    logger.info("🚀 Starting Skeleton System on port 5002...")
    
    # Cognitive System's blueprint and thought loop are already started by register_cognitive_system(app) in create_app()
    # No need to call start_thought_loop() here again.

    # Immune System's cleaner thread is already started by register_immune_system_shutdown(app) in create_app()
    # No need to call start_cleaner() here again.


    logger.info("🚀 All core background systems launched.")
    logger.info("ℹ️ To access the main web application, run 'python -m flask run' in a NEW terminal.")
    logger.info("ℹ️ Other systems (if separate apps): Nervous on 5001, Skeleton on 5002 (defaults)")
    logger.info("ℹ️ Press Ctrl+C in this terminal to initiate graceful shutdown of background systems.")


def stop_ailee_and_other_systems():
    logger.info("Initiating graceful shutdown of background systems...")
    # This function is also called within an app context (from __main__ block or CLI)
    # So `current_app` is fine to use here.
    
    # Stop AILEE Controller
    ailee_controller.stop()
    logger.info("🧠 AILEEController stopped.")

    # Stop Cognitive System thought loop
    stop_thought_loop() # Call the global stop_thought_loop function directly
    logger.info("🧠 Cognitive system thought loop stopped.")

    # Stop Immune System cleaner thread
    stop_immune_system_cleaner() # Call the global stop_immune_system_cleaner function directly
    logger.info("🛡️ Immune System cleaner thread stopped.")

    # For Flask apps run in threads, there's no direct 'stop' method.
    # They are usually stopped by the daemon=True flag when the main program exits.
    # However, for explicit shutdown, you might send a shutdown request or signal.
    # For this setup, relying on daemon threads ending with main process is common.
    # If you need explicit shutdown for Nervous/Skeleton, you'd need to implement
    # a shutdown endpoint or more complex signal handling.
    logger.info("Nervous and Skeleton Systems will shut down with the main process.")


# Entry point for `python -m peoples_coin.peoples_coin.run`
if __name__ == '__main__':
    logger.info("Entering __main__ block.")
    app = create_app()

    # FIX: Explicitly push an application context and call init_db() here
    # This ensures `current_app` is available and `init_db()` runs before background systems
    app_context = app.app_context()
    app_context.push() # Push the context manually

    try:
        # Initialize the database and create tables first
        logger.info("Attempting to initialize database tables...")
        init_db() # Call init_db() here to ensure tables are created on background system startup
        logger.info("Database initialization attempt completed.")
        
        # Populate test data AFTER database is initialized and tables exist
        populate_test_data() # Ensure test data is populated after DB init

        logger.info("Starting Peoples Coin application background systems...")
        start_ailee_and_other_systems()

        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected. Shutting down background systems...")
        stop_ailee_and_other_systems()
        logger.info("Background systems shut down gracefully.")
    except Exception as e:
        logger.critical(f"An unexpected error occurred in the main background process: {e}", exc_info=True)
        stop_ailee_and_other_systems() # Attempt graceful shutdown even on unexpected error
    finally:
        # Ensure the app context is popped when the main thread exits
        app_context.pop()


