import os
import secrets

class Config:
    """Centralized configuration settings for the application, loaded from environment variables."""

    # --- General & Security ---
    # Generates a secure, random key by default for development.
    # ALWAYS set this in your production environment.
    SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(16))
    DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

    # --- Logging ---
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
    LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    # --- Database ---
    # The factory will use this URI. Fallback to a local SQLite file for convenience.
    SQLALCHEMY_DATABASE_URI = os.environ.get('POSTGRES_DB_URI', 'sqlite:///../instance/peoples_coin.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DB_SUPPORTS_SKIP_LOCKED = os.environ.get("DB_SUPPORTS_SKIP_LOCKED", "true").lower() == "true"

    # --- Redis & Rate Limiting ---
    # A single Redis URL for all services (Celery, Caching, Rate Limiting).
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    RATELIMIT_STORAGE_URI = REDIS_URL
    RATELIMIT_DEFAULT = "100 per hour;20 per minute"

    # --- API Documentation ---
    SWAGGER = {
        'title': "People's Coin API",
        'uiversion': 3,
        'description': "API for the core systems of The People's Coin.",
    }

    # --- Celery Background Tasks ---
    USE_CELERY_FOR_GOODWILL = os.environ.get("USE_CELERY_FOR_GOODWILL", "false").lower() == "true"
    CELERY_BROKER_URL = REDIS_URL # Use the consolidated Redis URL
    CELERY_RESULT_BACKEND = REDIS_URL # Use the consolidated Redis URL
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
