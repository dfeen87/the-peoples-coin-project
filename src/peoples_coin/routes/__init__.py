from flask import Blueprint

# Import your blueprint instances here
from .auth import auth_bp
from .goodwill import goodwill_bp
from .blockchain import blockchain_bp

def register_routes(app):
    """
    Registers all blueprints under a main 'api' blueprint with versioning,
    then registers the 'api' blueprint on the app.
    """
    api_bp = Blueprint('api', __name__)

    # Register individual blueprints under the '/api/v1' namespace
    api_bp.register_blueprint(auth_bp, url_prefix='/auth')
    api_bp.register_blueprint(goodwill_bp, url_prefix='/goodwill')
    api_bp.register_blueprint(blockchain_bp, url_prefix='/blockchain')

    # Register the main API blueprint on the app with version prefix
    app.register_blueprint(api_bp, url_prefix='/api/v1')

