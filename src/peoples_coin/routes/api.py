import http
import logging
from functools import wraps # Keeping this import as it was in your original,
                            # even if not explicitly used in the shown functions.

from flask import Blueprint, request, jsonify, g
from pydantic import BaseModel, ValidationError, constr
from sqlalchemy.exc import IntegrityError
from flask_cors import CORS # IMPORT FLASK_CORS

from peoples_coin.extensions import db
from peoples_coin.utils.auth import require_firebase_token
from peoples_coin.models import UserAccount, UserWallet

logger = logging.getLogger(__name__)
user_api_bp = Blueprint("user_api", __name__)

# --- Initialize CORS for this Blueprint ---
# It's crucial to initialize CORS *after* the blueprint is created.
# This ensures all routes defined within `user_api_bp` get the CORS headers.
CORS(user_api_bp, resources={r"/*": {"origins": "https://brightacts.com"}})

# If you need to allow multiple origins (e.g., localhost for development), you can do:
# CORS(user_api_bp, resources={r"/*": {"origins": ["https://brightacts.com", "http://localhost:3000"]}})

# If you want to allow all origins (less secure for production, but good for testing all origins):
# CORS(user_api_bp, resources={r"/*": {"origins": "*"}})


# --- Pydantic Models ---
class WalletRegistrationSchema(BaseModel):
    username: constr(strip_whitespace=True, min_length=3, max_length=32)
    public_key: str
    encrypted_private_key: str


# --- Routes ---

@user_api_bp.route("/users/username-check/<username>", methods=["GET"])
def check_username_availability(username):
    """Check if a username is available in the database."""
    logger.info(f"Checking availability for username: {username}")
    try:
        # --- FIX APPLIED TO LINE 43 ---
        # Moved the filter expression directly inside the filter() call on one line.
        # This addresses potential subtle syntax/parsing issues that could lead to
        # an error like "filter:".
        exists = db.session.query(UserAccount).filter(UserAccount.username.ilike(username)).first()
        # --- END FIX ---

        return jsonify({"available": exists is None}), http.HTTPStatus.OK
    except Exception as e:
        logger.error(f"Error during username availability check: {e}", exc_info=True)
        return jsonify({"available": False, "error": "Database query failed"}), http.HTTPStatus.INTERNAL_SERVER_ERROR


@user_api_bp.route("/users/register-wallet", methods=["POST"])
@require_firebase_token
def register_user_wallet():
    """
    Creates a new UserAccount and a linked UserWallet in the database,
    based on the authenticated Firebase user.
    """
    firebase_user = g.firebase_user
    logger.info(f"Registering wallet for Firebase UID: {firebase_user.get('uid')}")

    try:
        payload = request.get_json()
        if not payload:
            return jsonify(error="Missing JSON body"), http.HTTPStatus.BAD_REQUEST

        validated_data = WalletRegistrationSchema(**payload)

        # Before creating a new user, it's good practice to also check if
        # email or firebase_uid are already in use, although your IntegrityError
        # handler will catch this at the DB level.
        # This check might be redundant if Firebase Auth ensures UID uniqueness already.
        existing_user_by_email = db.session.query(UserAccount).filter_by(email=firebase_user['email']).first()
        if existing_user_by_email:
            return jsonify(error="User with this email already exists."), http.HTTPStatus.CONFLICT

        existing_user_by_uid = db.session.query(UserAccount).filter_by(firebase_uid=firebase_user['uid']).first()
        if existing_user_by_uid:
            return jsonify(error="User with this Firebase UID already exists."), http.HTTPStatus.CONFLICT


        new_user = UserAccount(
            firebase_uid=firebase_user['uid'],
            email=firebase_user['email'],
            username=validated_data.username
        )
        db.session.add(new_user)
    
        # Use flush() for cases where you need the ID *before* commit (e.g., for related objects)
        # If your database is configured for UUID defaults, this will retrieve the ID from the DB
        # after the insert, before the commit
        db.session.flush()

        new_wallet = UserWallet(
            user_id=new_user.id,
            public_address=validated_data.public_key,
            encrypted_private_key=validated_data.encrypted_private_key,
            is_primary=True
        )
        db.session.add(new_wallet)
        db.session.commit()

        logger.info(f"User '{validated_data.username}' registered successfully with ID: {new_user.id}")
        return jsonify({
            "message": "User and wallet created successfully",
            "userId": str(new_user.id) # Ensure UUID is converted to string for JSON
        }), http.HTTPStatus.CREATED

    except ValidationError as ve:
        logger.warning(f"Validation failed: {ve.errors()}")
        return jsonify(error="Invalid input", details=ve.errors()), http.HTTPStatus.UNPROCESSABLE_ENTITY

    except IntegrityError as e:
        db.session.rollback()
        # This catch-all for IntegrityError is good. PostgreSQL will indicate
        # which unique constraint failed. You could parse `e` to give a more
        # specific error message (e.g., "Email already registered" vs "Wallet address taken").
        logger.warning(f"Integrity error (duplicate): {e}")
        return jsonify(error="User with this email, UID, or wallet address already exists."), http.HTTPStatus.CONFLICT

    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error during registration: {e}", exc_info=True)
        return jsonify(error="An internal server error occurred."), http.HTTPStatus.INTERNAL_SERVER_ERROR


@user_api_bp.route("/profile", methods=["GET"])
@require_firebase_token
def get_user_profile():
    """Returns the authenticated user's profile information."""
    user = g.user
    if not user:
        return jsonify(error="User not authenticated or found"), http.HTTPStatus.UNAUTHORIZED
    # Assuming user.to_dict() correctly serializes the UserAccount object
    return jsonify(user.to_dict()), http.HTTPStatus.OK
