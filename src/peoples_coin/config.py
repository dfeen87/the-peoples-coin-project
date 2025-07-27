import os
import secrets

class Config:
    """
    Base configuration class with defaults and environment variable integration.
    """

    # --- General & Security ---
    SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(16))
    DEBUG = False

    # --- Logging ---
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
    LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    # --- Database Configuration ---
    DB_USER = os.environ.get('DB_USER')
    DB_PASS = os.environ.get('DB_PASS')
    DB_NAME = os.environ.get('DB_NAME')
    INSTANCE_CONNECTION_NAME = os.environ.get('INSTANCE_CONNECTION_NAME')

    if all([DB_USER, DB_PASS, DB_NAME, INSTANCE_CONNECTION_NAME]):
        # Cloud SQL PostgreSQL connection via Unix socket
        SQLALCHEMY_DATABASE_URI = (
            f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@/"
            f"{DB_NAME}?host=/cloudsql/{INSTANCE_CONNECTION_NAME}"
        )
    else:
        # Fallback for local development (SQLite)
        SQLALCHEMY_DATABASE_URI = 'sqlite:///../instance/peoples_coin.db'
        print("WARNING: Cloud SQL environment variables not set. Using local SQLite database.")

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DB_SUPPORTS_SKIP_LOCKED = os.environ.get("DB_SUPPORTS_SKIP_LOCKED", "true").lower() == "true"

    # --- Redis & Rate Limiting ---
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    RATELIMIT_STORAGE_URI = REDIS_URL
    RATELIMIT_DEFAULT = "100 per hour;20 per minute"

    # --- Swagger API Documentation ---
    SWAGGER = {
        'title': "People's Coin API",
        'uiversion': 3,
        'description': "API for the core systems of The People's Coin.",
    }

    # --- Celery Background Tasks ---
    USE_CELERY_FOR_GOODWILL = os.environ.get("USE_CELERY_FOR_GOODWILL", "false").lower() == "true"
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
    CELERY_TASK_ACKS_LATE = True
    CELERY_WORKER_PREFETCH_MULTIPLIER = 1

    # --- AILEE Processing Config ---
    AILEE_ISP = float(os.environ.get("AILEE_ISP", 0.75))
    AILEE_ETA = float(os.environ.get("AILEE_ETA", 0.9))
    AILEE_ALPHA = float(os.environ.get("AILEE_ALPHA", 0.005))
    AILEE_V0 = float(os.environ.get("AILEE_V0", 0.1))
    AILEE_MAX_WORKERS = int(os.environ.get("AILEE_MAX_WORKERS", 2))
    AILEE_BATCH_SIZE = int(os.environ.get("AILEE_BATCH_SIZE", 5))
    AILEE_RETRIES = int(os.environ.get("AILEE_RETRIES", 3))
    AILEE_RETRY_DELAY = int(os.environ.get("AILEE_RETRY_DELAY", 2))

    # --- Love Resonance Equation Parameters ---
    L_ETA_L = float(os.environ.get("L_ETA_L", 0.8))

    # --- Consensus System Config ---
    POW_DIFFICULTY = os.environ.get("POW_DIFFICULTY", "0000")

    # --- Immune System Config ---
    IMMUNE_QUARANTINE_TIME_SEC = int(os.environ.get("IMMUNE_QUARANTINE_TIME_SEC", 300))
    IMMUNE_MAX_INVALID_ATTEMPTS = int(os.environ.get("IMMUNE_MAX_INVALID_ATTEMPTS", 5))

    # --- CORS Origins (comma-separated string) ---
    # Split by comma, strip whitespace, filter out empty strings
    raw_origins = os.environ.get('CORS_ORIGINS', 'https://brightacts.com')
    CORS_ORIGINS = [origin.strip() for origin in raw_origins.split(',') if origin.strip()]


class ProductionConfig(Config):
    DEBUG = False
    # Add any production-specific overrides here, e.g., stricter security settings


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///../instance/peoples_coin_dev.db'
    # Allow localhost for dev and your frontend domain
    CORS_ORIGINS = ['http://localhost:3000', 'https://brightacts.com']

