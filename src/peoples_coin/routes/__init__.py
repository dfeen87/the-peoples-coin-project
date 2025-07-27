# Import all the blueprint instances from your route files
from .api import user_api_bp
from .auth import auth_bp
from .goodwill import goodwill_bp
from .blockchain import blockchain_bp

def register_routes(app):
    """
    Registers all blueprints on the main Flask app.
    The version prefix is now handled in the factory.
    """
    app.register_blueprint(user_api_bp, url_prefix='/api/v1')
    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(goodwill_bp, url_prefix='/api/v1/goodwill')
    app.register_blueprint(blockchain_bp, url_prefix='/api/v1/blockchain')

