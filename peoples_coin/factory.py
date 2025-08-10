import os
import logging
from flask import Flask, request, jsonify
from peoples_coin.extensions import db, migrate, cors, limiter, swagger, make_celery
from peoples_coin.utils.recaptcha_verify import verify_recaptcha

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    """Creates and configures the Flask application."""
    app = Flask(__name__, instance_relative_config=True)

    try:
        db_user = os.environ.get("DB_USER")
        db_pass = os.environ.get("DB_PASS")
        db_name = os.environ.get("DB_NAME")
        instance_connection_name = os.environ.get("INSTANCE_CONNECTION_NAME")

        if not all([db_user, db_pass, db_name, instance_connection_name]):
            raise ValueError("One or more database environment variables are not set.")

        # Correct URI for connecting to the Cloud SQL Auth Proxy socket
        db_uri = (
           f"postgresql+pg8000://{db_user}:{db_pass}@/{db_name}"
           f"?unix_sock=/cloudsql/{instance_connection_name}/.s.PGSQL.5432"
        )
        
        app.config.from_mapping(
            SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret"),
            SQLALCHEMY_DATABASE_URI=db_uri,
            SQLALCHEMY_TRACK_MODIFICATIONS=False, # Set to None for future versions
        )
        logger.info("✅ App configured with Cloud SQL Unix socket URI.")

    except Exception as e:
        logger.critical(f"🚨 FAILED TO CONFIGURE DATABASE: {e}")
        raise

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app)
    limiter.init_app(app)
    swagger.init_app(app)
    logger.info("✅ Extensions initialized.")
    
    # Initialize Celery if configured
    if "CELERY_BROKER_URL" in os.environ:
        make_celery(app)
        logger.info("✅ Celery initialized.")

    # Register blueprints
    with app.app_context():
        from peoples_coin.routes import user_api_bp  # Your existing user API blueprint
        from peoples_coin.routes import status_routes  # New status routes blueprint

        app.register_blueprint(user_api_bp)
        app.register_blueprint(status_routes.status_bp)  # Register status routes blueprint

        logger.info("✅ Blueprints registered successfully.")

    # Health check route
    @app.route("/health")
    def health():
        return {"status": "ok"}, 200

    # Example signup route
    @app.route("/signup", methods=["POST"])
    def signup():
        data = request.json or {}
        recaptcha_token = data.get("recaptchaToken")
        if not recaptcha_token:
            return jsonify({"error": "Missing reCAPTCHA token"}), 400
        
        is_valid, message = verify_recaptcha(recaptcha_token, expected_action="submit")
        
        if not is_valid:
            return jsonify({"error": "reCAPTCHA verification failed", "details": message}), 400
        
        # Add your user creation logic here
        
        return jsonify({"message": "User signed up successfully"}), 201

    logger.info("🚀 Flask app created successfully!")
    return app

