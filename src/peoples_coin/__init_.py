import os
import atexit
from flask import Flask
from .config import Config # Assume you have a config.py

# --- Import System Components ---
# Import the database instance and all your custom system classes
from .db.db import db
from .systems.immune_system import ImmuneSystem
from .systems.cognitive_system import CognitiveSystem, cognitive_bp
from .systems.endocrine_system import AILEEController
from .systems.circulatory_system import CirculatorySystem
from .systems.nervous_system import nervous_bp # Your newly integrated blueprint
from .systems.metabolic_system import metabolic_bp # And any other blueprints

# --- Instantiate Global System Objects ---
# These act as singletons for the lifetime of the application.
immune_system = ImmuneSystem()
cognitive_system = CognitiveSystem()
ailee_controller = AILEEController()
circulatory_system = CirculatorySystem()

def create_app(config_class=Config):
    """
    The main application factory. Creates and configures the Flask app
    and all associated systems.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # --- Initialize Extensions and Systems in Order ---

    # 1. Initialize the database first, as other systems depend on it.
    db.init_app(app)

    # 2. Initialize the core systems, passing the app and db context as needed.
    immune_system.init_app(app)
    cognitive_system.init_app(app)
    circulatory_system.init_app(app, db)
    
    # 3. Initialize the background worker system last, as it may use other systems.
    # The AILEEController will run within the fully configured app context.
    with app.app_context():
        ailee_controller.init_app(app, max_workers=app.config.get("AILEE_MAX_WORKERS", 2))

    # --- Register Blueprints ---
    # Register all the API endpoints from your different systems.
    app.register_blueprint(nervous_bp)
    app.register_blueprint(metabolic_bp)
    app.register_blueprint(cognitive_bp)
    # ... register any other blueprints ...

    # --- Register Graceful Shutdown Hooks ---
    # Ensure background threads are stopped cleanly when the app exits.
    atexit.register(cognitive_system.stop_background_loop)
    atexit.register(ailee_controller.stop)
    
    print("==============================================")
    print("  The People's Coin System is coming online.  ")
    print("==============================================")

    return app

