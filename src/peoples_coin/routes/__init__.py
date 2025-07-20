from flask import Blueprint
from .auth import auth_bp
from .goodwill import goodwill_bp
from .blockchain import blockchain_bp

api = Blueprint('api', __name__)

api.register_blueprint(auth_bp)
api.register_blueprint(goodwill_bp)
api.register_blueprint(blockchain_bp)

