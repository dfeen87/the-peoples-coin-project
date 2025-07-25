# src/peoples_coin/routes/api.py
import http
import logging
from functools import wraps

from flask import Blueprint, request, jsonify, g
from pydantic import BaseModel, ValidationError

from peoples_coin.extensions import db
from peoples_coin.utils.auth import require_api_key, require_firebase_token

logger = logging.getLogger(__name__)
api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

# --- Pydantic Validation Decorator (Excellent Pattern!) ---
def validate_with(model: BaseModel):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                g.validated_data = model(**request.get_json(force=True))
            except ValidationError as e:
                return jsonify(error="Validation error", details=e.errors()), http.HTTPStatus.BAD_REQUEST
            except Exception:
                return jsonify(error="Malformed JSON request"), http.HTTPStatus.BAD_REQUEST
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- API Routes ---

@api_bp.route("/health", methods=["GET"])
def health():
    """Basic health check to confirm the service is running."""
    return jsonify(status="healthy"), http.HTTPStatus.OK

@api_bp.route("/readiness", methods=["GET"])
def readiness():
    """Readiness probe to check dependencies like the database."""
    try:
        with db.engine.connect() as connection:
            connection.execute("SELECT 1")
        return jsonify(status="ready"), http.HTTPStatus.OK
    except Exception as e:
        logger.error(f"Readiness check failed: {e}", exc_info=True)
        return jsonify(status="error", message="Database connection failed"), http.HTTPStatus.SERVICE_UNAVAILABLE

@api_bp.route("/profile", methods=["GET"])
@require_firebase_token
def get_user_profile():
    """Returns the authenticated user's profile information from the database."""
    user = g.user
    return jsonify({
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "balance": str(user.balance),
        "goodwill_coins": user.goodwill_coins,
        "bio": user.bio,
        "profile_image_url": user.profile_image_url,
        "created_at": user.created_at.isoformat()
    }), http.HTTPStatus.OK

# Add other routes here...
