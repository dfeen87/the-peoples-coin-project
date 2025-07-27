import http
import logging
from functools import wraps

from flask import Blueprint, request, jsonify, g
from pydantic import BaseModel, ValidationError

from peoples_coin.extensions import db
from peoples_coin.utils.auth import require_api_key, require_firebase_token
from peoples_coin.models import UserAccount # Ensure this import is present

logger = logging.getLogger(__name__)
api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

# The conflicting CORS line has been removed from here.
# Your main create_app() function now handles CORS correctly.

def validate_with(model: BaseModel):
    """Pydantic validation decorator for request bodies."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                if not request.is_json:
                    return jsonify(error="Invalid request: Missing JSON body"), http.HTTPStatus.BAD_REQUEST
                g.validated_data = model(**request.get_json())
            except ValidationError as e:
                logger.warning(f"Validation error: {e.errors()}")
                return jsonify(error="Validation error", details=e.errors()), http.HTTPStatus.BAD_REQUEST
            except Exception as e:
                logger.error(f"Malformed JSON request: {e}", exc_info=True)
                return jsonify(error="Malformed JSON request"), http.HTTPStatus.BAD_REQUEST
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# --- API Routes ---

@api_bp.route("/health", methods=["GET"])
def health():
    """Basic health check to confirm the service is running."""
    logger.info("Health check requested.")
    return jsonify(status="healthy"), http.HTTPStatus.OK


@api_bp.route("/readiness", methods=["GET"])
def readiness():
    """Readiness probe to check dependencies like the database."""
    logger.info("Readiness check requested.")
    try:
        with db.engine.connect() as connection:
            connection.execute(db.text("SELECT 1"))
        logger.info("Readiness check successful: Database connected.")
        return jsonify(status="ready"), http.HTTPStatus.OK
    except Exception as e:
        logger.error(f"Readiness check failed: {e}", exc_info=True)
        return jsonify(status="error", message="Database connection failed"), http.HTTPStatus.SERVICE_UNAVAILABLE


# --- User-related Routes ---

@api_bp.route("/users/username-check/<username>", methods=["GET"])
def check_username_availability(username):
    """Checks if a username is available in the database."""
    logger.info(f"Checking database for username availability for: {username}")
    try:
        # Query the database for a user with the given username (case-insensitive)
        user_exists = db.session.query(UserAccount).filter(UserAccount.username.ilike(username)).first()
        
        # If user_exists is None, the username is available.
        is_available = (user_exists is None)
        
        logger.info(f"Username '{username}' is available: {is_available}")
        return jsonify({"available": is_available}), http.HTTPStatus.OK

    except Exception as e:
        logger.error(f"Database error while checking username '{username}': {e}", exc_info=True)
        # Return false by default on error to be safe
        return jsonify({"available": False, "error": "Database query failed"}), http.HTTPStatus.INTERNAL_SERVER_ERROR


@api_bp.route("/users/register-wallet", methods=["POST"])
# @validate_with(UserRegistrationModel) # Example usage of the decorator
# @require_firebase_token
def register_user_wallet():
    """Placeholder for user registration/wallet creation."""
    logger.info("Attempting to register new user wallet.")
    # In a real app, you would save data from request.get_json() to your database here.
    return jsonify({"message": "User wallet registration simulated successfully"}), http.HTTPStatus.CREATED


@api_bp.route("/profile", methods=["GET"])
@require_firebase_token
def get_user_profile():
    """Returns the authenticated user's profile information."""
    user = g.user
    logger.info(f"Fetching profile for user: {user.id if user else 'unknown'}")

    if not user:
        return jsonify(error="User not authenticated or found"), http.HTTPStatus.UNAUTHORIZED

    return jsonify({
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "balance": str(user.balance),
        "goodwill_coins": user.goodwill_coins,
        "bio": user.bio,
        "profile_image_url": user.profile_image_url,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat() if user.updated_at else None
    }), http.HTTPStatus.OK

