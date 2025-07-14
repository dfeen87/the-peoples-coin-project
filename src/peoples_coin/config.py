kimport os

class Config:
    """Base configuration settings for the Flask application."""

    # General Config
    SECRET_KEY = os.environ.get('SECRET_KEY', 'a-very-secret-key-that-you-should-change')
    DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
    LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

    # Database
    # Leave SQLALCHEMY_DATABASE_URI out here to be set explicitly in __init__.py or env
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # API Keys for Skeleton system (custom app usage)
    API_KEYS = set(os.environ.get("SKELETON_API_KEYS", "default-key").split(","))

    # AILEE Processing Config
    AILEE_ISP = float(os.environ.get("AILEE_ISP", 0.75))
    AILEE_ETA = float(os.environ.get("AILEE_ETA", 0.9))
    AILEE_ALPHA = float(os.environ.get("AILEE_ALPHA", 0.005))
    AILEE_V0 = float(os.environ.get("AILEE_V0", 0.1))
    AILEE_MAX_WORKERS = int(os.environ.get("AILEE_MAX_WORKERS", 2))

    AILEE_BATCH_SIZE = int(os.environ.get("AILEE_BATCH_SIZE", 5))
    AILEE_RETRIES = int(os.environ.get("AILEE_RETRIES", 3))
    AILEE_RETRY_DELAY = int(os.environ.get("AILEE_RETRY_DELAY", 2))
    DB_SUPPORTS_SKIP_LOCKED = os.environ.get("DB_SUPPORTS_SKIP_LOCKED", "True").lower() == "true"

    # Love Resonance Equation Parameters
    L_ETA_L = float(os.environ.get("L_ETA_L", 0.8))

    # Celery Config - add these if you want celery toggling and tuning
    USE_CELERY_FOR_GOODWILL = os.environ.get("USE_CELERY_FOR_GOODWILL", "False").lower() == "true"
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
    CELERY_TASK_ACKS_LATE = True
    CELERY_WORKER_PREFETCH_MULTIPLIER = 1

    # Consensus System Config (domain specific)
    POW_DIFFICULTY = os.environ.get("POW_DIFFICULTY", "0000")

