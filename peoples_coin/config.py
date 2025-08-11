import os
import secrets
import sys

class Config:
    """
    Unified configuration class for development and production environments.
    Reads settings primarily from environment variables, with sensible defaults.
    """

    # --- General & Security ---
    SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(16))
    FLASK_ENV = os.environ.get("FLASK_ENV", "development").lower()
    DEBUG = FLASK_ENV != "production"

    # --- Logging ---
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
    LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    # --- Database Configuration ---
    DB_USER = os.environ.get('DB_USER')
    DB_PASS = os.environ.get('DB_PASS')
    DB_NAME = os.environ.get('DB_NAME')
    INSTANCE_CONNECTION_NAME = os.environ.get('INSTANCE_CONNECTION_NAME')

    if INSTANCE_CONNECTION_NAME:
        parts = INSTANCE_CONNECTION_NAME.split(':')
        if len(parts) != 3 or any(not part.strip() for part in parts):
            print(
                f"ERROR: INSTANCE_CONNECTION_NAME must be in 'project:region:instance' format but got '{INSTANCE_CONNECTION_NAME}'",
                file=sys.stderr
            )
            sys.exit(1)
    else:
        print("ERROR: INSTANCE_CONNECTION_NAME environment variable is NOT set.", file=sys.stderr)
        sys.exit(1)

    if all([DB_USER, DB_PASS, DB_NAME, INSTANCE_CONNECTION_NAME]):
        SQLALCHEMY_DATABASE_URI = (
            f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@/"
            f"{DB_NAME}?host=/cloudsql/{INSTANCE_CONNECTION_NAME}"
        )
    else:
        # Local fallback: different SQLite DB for dev vs prod
        db_name = 'peoples_coin_dev.db' if DEBUG else 'peoples_coin.db'
        SQLALCHEMY_DATABASE_URI = f"sqlite:///../instance/{db_name}"
        print(f"WARNING: Cloud SQL environment variables not fully set. Using local SQLite database: {db_name}")

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Support for DB skip locked (used in Postgres locking queries)
    DB_SUPPORTS_SKIP_LOCKED = os.environ.get("DB_SUPPORTS_SKIP_LOCKED", "true").lower() == "true"

    # --- Redis Configuration ---
    REDIS_HOST = os.environ.get("REDIS_HOST", "10.128.0.12")
    REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
    REDIS_DB = int(os.environ.get("REDIS_DB", 0))
    REDIS_URL = os.environ.get("REDIS_URL") or f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

    # --- Rate Limiting ---
    RATELIMIT_STORAGE_URI = REDIS_URL
    RATELIMIT_DEFAULT = os.environ.get("RATELIMIT_DEFAULT", "100 per hour;20 per minute")

    # --- CORS Origins ---
    CORS_ORIGINS = [
        "https://brightacts.com",
        "https://peoples-coin-service-105378934751.us-central1.run.app",
        "http://localhost:5000",
        "http://localhost:8080",
    ]

    # --- Firebase Admin ---
    FIREBASE_CREDENTIAL_PATH = os.environ.get("FIREBASE_CREDENTIAL_PATH", "serviceAccountKey.json")

