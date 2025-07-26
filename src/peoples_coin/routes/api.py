import http # Used for HTTPStatus codes
import logging
from functools import wraps

from flask import Blueprint, request, jsonify, g # Removed make_response as it's no longer needed for this file
from pydantic import BaseModel, ValidationError

from peoples_coin.extensions import db
from peoples_coin.utils.auth import require_api_key, require_firebase_token # Assuming these exist

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
        # Attempt to connect to the database
        with db.engine.connect() as connection:
            connection.execute(db.text("SELECT 1")) # Use db.text for SQLAlchemy 2.0+
        logger.info("Readiness check successful: Database connected.")
        return jsonify(status="ready"), http.HTTPStatus.OK
    except Exception as e:
        logger.error(f"Readiness check failed: {e}", exc_info=True)
        return jsonify(status="error", message="Database connection failed"), http.HTTPStatus.SERVICE_UNAVAILABLE

# --- User-related Routes ---

@api_bp.route("/users/username-check/<username>", methods=["GET"])
def check_username_availability(username):
    """
    Checks if a username is available.
    Removed direct CORS headers; Flask-CORS initialized in factory.py will handle this globally.
    """
    logger.info(f"Checking username availability for: {username}")
    # In a real application, you would query your database here
    # For now, let's simulate a username being taken (e.g., 'brightacts' is taken)
    is_available = (username.lower() != "brightacts")

    if is_available:
        logger.info(f"Username '{username}' is available.")
    else:
        logger.info(f"Username '{username}' is NOT available.")
    
    return jsonify({"available": is_available}), http.HTTPStatus.OK

# Placeholder for user registration/wallet creation
# This route would typically receive data from your Flutter app's sign-up screen
@api_bp.route("/users/register-wallet", methods=["POST"])
# @validate_with(UserRegistrationModel) # Example: You'd define a Pydantic model for this
# @require_firebase_token # This would ensure the user is authenticated via Firebase
def register_user_wallet():
    logger.info("Attempting to register new user wallet.")
    # Example of accessing validated data if using the decorator:
    # data = g.validated_data
    # username = data.username
    # public_key = data.public_key
    # encrypted_private_key = data.encrypted_private_key
    # recaptcha_token = data.recaptcha_token

    # In a real app, you'd save this to your database (user_accounts, user_wallets)
    # For now, just a dummy response
    return jsonify({"message": "User wallet registration simulated successfully"}), http.HTTPStatus.CREATED


@api_bp.route("/profile", methods=["GET"])
@require_firebase_token # Ensures a Firebase authenticated user
def get_user_profile():
    """Returns the authenticated user's profile information from the database."""
    logger.info(f"Fetching profile for user: {g.user.id}")
    user = g.user # Assuming g.user is set by require_firebase_token decorator
    
    if not user:
        logger.warning("Attempted to get profile for unauthenticated user.")
        return jsonify(error="User not authenticated or found"), http.HTTPStatus.UNAUTHORIZED

    return jsonify({
        "id": str(user.id), # Convert UUID to string
        "email": user.email,
        "username": user.username,
        "balance": str(user.balance), # Convert Decimal to string
        "goodwill_coins": user.goodwill_coins,
        "bio": user.bio,
        "profile_image_url": user.profile_image_url,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat() if user.updated_at else None # Handle potential null
    }), http.HTTPStatus.OK

# --- Add other routes here based on your schema and API design ---
# Example: Goodwill Actions, Proposals, Votes, Ledger, etc.

# Example Pydantic models (you'd define these in a separate models.py or similar)
# class UserRegistrationModel(BaseModel):
#     username: str
#     public_key: str
#     encrypted_private_key: str
#     recaptcha_token: str
#     email: str # Assuming email is part of registration
#     password: str # Assuming password is part of registration

