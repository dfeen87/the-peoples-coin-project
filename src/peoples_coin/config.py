import os
import secrets

class Config:
    """
    Unified configuration class for both development and production.
    """

    # --- General & Security ---
    SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(16))
    DEBUG = os.environ.get("FLASK_ENV", "development") != "production"

    # --- Logging ---
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
    LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    # --- Database Configuration ---
    DB_USER = os.environ.get('DB_USER')
    DB_PASS = os.environ.get('DB_PASS')
    DB_NAME = os.environ.get('DB_NAME')
    INSTANCE_CONNECTION_NAME = os.environ.get('INSTANCE_CONNECTION_NAME')

    if all([DB_USER, DB_PASS, DB_NAME, INSTANCE_CONNECTION_NAME]):
        SQLALCHEMY_DATABASE_URI = (
            f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@/"
            f"{DB_NAME}?host=/cloudsql/{INSTANCE_CONNECTION_NAME}"
        )
    else:
        # Use a different database for dev vs prod to avoid data loss
        db_name = 'peoples_coin_dev.db' if DEBUG else 'peoples_coin.db'
        SQLALCHEMY_DATABASE_URI = f'sqlite:///../instance/{db_name}'
        print(f"WARNING: Cloud SQL env vars not set. Using local SQLite: {db_name}")

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DB_SUPPORTS_SKIP_LOCKED = os.environ.get("DB_SUPPORTS_SKIP_LOCKED", "true").lower() == "true"

    # --- Redis & Rate Limiting ---
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    RATELIMIT_STORAGE_URI = REDIS_URL
    RATELIMIT_DEFAULT = "100 per hour;20 per minute"

    # --- THIS IS THE MAIN FIX ---
    # A single, unified list of allowed domains for CORS.
    # This list will be used for both development and production.
    CORS_ORIGINS = [
        "https://brightacts.com",  # Your primary production domain
        "https://peoples-coin-service-105378934751.us-central1.run.app", # Your Firebase domain
        # Add common localhost ports for local Flutter development
        "http://localhost:5000",
        "http://localhost:8080",
        # You can add the specific port your Flutter app runs on if it's consistent
        # e.g., "http://localhost:54321" 
    ]
    # If you have a custom domain for your Firebase app, add it here too:
    # e.g., "https://app.brightacts.com"

    # --- Firebase Admin ---
    # This path is usually configured via environment variables in production
    FIREBASE_CREDENTIAL_PATH = os.environ.get("FIREBASE_CREDENTIAL_PATH")

# --- REMOVED ProductionConfig and DevelopmentConfig ---
# We now use the single, unified Config class to reduce complexity.
# Your create_app function should be updated to just use:
# app.config.from_object('peoples_coin.config.Config')

