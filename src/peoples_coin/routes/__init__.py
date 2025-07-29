# src/peoples_coin/routes/__init__.py

"""
This module imports all blueprint instances from route modules
and provides a function to register them on the Flask app
with proper URL prefixes for API versioning.
"""

from .api import user_api_bp
from .auth import auth_bp
from .goodwill import goodwill_bp
from .blockchain import blockchain_bp

def register_routes(app):
    """
    Register all blueprints with the Flask app.

    Each blueprint is registered with a versioned URL prefix to
    support API versioning and keep routes organized.
    """
    app.register_blueprint(user_api_bp, url_prefix='/api/v1')
    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(goodwill_bp, url_prefix='/api/v1/goodwill')
    app.register_blueprint(blockchain_bp, url_prefix='/api/v1/blockchain')

