import os

class Config:
    """Base configuration settings for the Flask application."""
    # General Config
    SECRET_KEY = os.environ.get('SECRET_KEY', 'a-very-secret-key-that-you-should-change')
    DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

    # Database
    # This is now a simple, relative path. Flask will automatically place this
    # inside the 'instance' folder because of the settings in create_app().
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///peoples_coin.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Custom Application Systems Config
    API_KEYS = set(os.environ.get("SKELETON_API_KEYS", "default-key").split(","))
    AILEE_MAX_WORKERS = int(os.environ.get("AILEE_MAX_WORKERS", 2))
    POW_DIFFICULTY = os.environ.get("POW_DIFFICULTY", "0000")

