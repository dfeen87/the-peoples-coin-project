import os

class Config:
    """Base configuration settings for the Flask application."""
    # General Config
    SECRET_KEY = os.environ.get('SECRET_KEY', 'a-very-secret-key-that-you-should-change')
    DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

    # Database
    # --- CRITICAL FIX: Remove SQLALCHEMY_DATABASE_URI from here ---
    # It will be set explicitly with an absolute path in __init__.py
    SQLALCHEMY_TRACK_MODIFICATIONS = False # Keep this setting

    # Custom Application Systems Config
    API_KEYS = set(os.environ.get("SKELETON_API_KEYS", "default-key").split(","))

    # --- AILEE Configuration Parameters ---
    AILEE_ISP = float(os.environ.get("AILEE_ISP", 0.75))
    AILEE_ETA = float(os.environ.get("AILEE_ETA", 0.9))
    AILEE_ALPHA = float(os.environ.get("AILEE_ALPHA", 0.005))
    AILEE_V0 = float(os.environ.get("AILEE_V0", 0.1))
    AILEE_MAX_WORKERS = int(os.environ.get("AILEE_MAX_WORKERS", 2))
    
    AILEE_BATCH_SIZE = int(os.environ.get("AILEE_BATCH_SIZE", 5))
    AILEE_RETRIES = int(os.environ.get("AILEE_RETRIES", 3))
    AILEE_RETRY_DELAY = int(os.environ.get("AILEE_RETRY_DELAY", 2))

    # --- L (Love Resonance) Equation Parameters ---
    L_ETA_L = float(os.environ.get("L_ETA_L", 0.8))

    # Consensus System Config
    POW_DIFFICULTY = os.environ.get("POW_DIFFICULTY", "0000")


