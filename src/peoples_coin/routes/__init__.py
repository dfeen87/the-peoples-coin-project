from flask import Blueprint

# Import your blueprint instances here
from .auth import auth_bp
from .goodwill import goodwill_bp
from .blockchain import blockchain_bp
# --- THIS IS THE NEW LINE ---
from .api import user_api_bp # Import the blueprint from api.py

def register_routes(app):
    """
    Registers all blueprints under a main 'api' blueprint with versioning,
    then registers the 'api' blueprint on the app.
    """
    # This main_api_bp acts as a container for all v1 routes
    main_api_bp = Blueprint('api', __name__)

    # Register individual blueprints under the '/api/v1' namespace
    main_api_bp.register_blueprint(auth_bp, url_prefix='/auth')
    main_api_bp.register_blueprint(goodwill_bp, url_prefix='/goodwill')
    main_api_bp.register_blueprint(blockchain_bp, url_prefix='/blockchain')
    # --- THIS IS THE NEW LINE ---
    # Register the user/profile routes from api.py.
    # Since the routes in api.py already contain '/users', we don't need a url_prefix here.
    main_api_bp.register_blueprint(user_api_bp)

    # Register the main API blueprint on the app with the version prefix
    app.register_blueprint(main_api_bp, url_prefix='/api/v1')

