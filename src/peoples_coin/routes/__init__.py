from flask import Blueprint

# Import your blueprint instances here
from .auth import auth_bp
from .goodwill import goodwill_bp
from .blockchain import blockchain_bp

def register_routes(app):
    api_bp = Blueprint('api', __name__)

    # Register all your blueprints under the `api` prefix (optional)
    api_bp.register_blueprint(auth_bp, url_prefix='/auth')
    api_bp.register_blueprint(goodwill_bp, url_prefix='/goodwill')
    api_bp.register_blueprint(blockchain_bp, url_prefix='/blockchain')

    # Register the main api blueprint to app
    app.register_blueprint(api_bp, url_prefix='/api/v1')

