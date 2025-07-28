import os
import logging
from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

# Initialize extensions
db = SQLAlchemy()

def create_app():
    # Create Flask app instance
    app = Flask(__name__)

    # Load config from environment or fallback
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///local.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret"),
    )

    # Setup CORS
    CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("✅ Flask app instance created and configured.")

    # Initialize extensions
    db.init_app(app)

    # Register blueprints (example only — replace with yours)
    try:
        from peoples_coin.routes import api_blueprint
        app.register_blueprint(api_blueprint, url_prefix="/api")
        logger.info("✅ Blueprint registered.")
    except ImportError as e:
        logger.warning("⚠️ No blueprint registered. Reason: %s", str(e))

    # Basic health check
    @app.route("/health")
    def health():
        return {"status": "ok"}, 200

    return app

