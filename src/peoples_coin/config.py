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
    # Set your Cloud SQL instance connection name explicitly here as default
    INSTANCE_CONNECTION_NAME = os.environ.get('INSTANCE_CONNECTION_NAME', 'peoples-coin-cluster-final')

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

    # Use explicit host and port for Redis so you can override with your VPC Redis IP easily
    REDIS_HOST = os.environ.get("REDIS_HOST", "10.128.0.4")
    REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
    REDIS_DB = int(os.environ.get("REDIS_DB", 0))

    # Construct Redis URL dynamically from host/port/db
    REDIS_URL = os.environ.get("REDIS_URL") or f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

    # Rate limiting config using Redis as backend storage
    RATELIMIT_STORAGE_URI = REDIS_URL
    RATELIMIT_DEFAULT = "100 per hour;20 per minute"
    
    # --- CORS Origins ---
    CORS_ORIGINS = [
        "https://brightacts.com",  # Your primary production domain
        "https://peoples-coin-service-105378934751.us-central1.run.app", # Your deployed backend URL
        "http://localhost:5000",
        "http://localhost:8080",
    ]

    # --- Firebase Admin ---
    FIREBASE_CREDENTIAL_PATH = os.environ.get("FIREBASE_CREDENTIAL_PATH", "serviceAccountKey.json")
