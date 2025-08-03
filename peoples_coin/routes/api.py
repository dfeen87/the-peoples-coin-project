import http
import logging
from functools import wraps

from flask import Blueprint, request, jsonify, g
from pydantic import BaseModel, ValidationError, constr
from sqlalchemy.exc import IntegrityError

from peoples_coin.extensions import db
from peoples_coin.utils.auth import require_firebase_token
from peoples_coin.models import UserAccount, UserWallet

logger = logging.getLogger(__name__)

# --- Blueprint Setup ---
user_api_bp = Blueprint("user_api", __name__)


# --- Pydantic Schemas ---
class WalletRegistrationSchema(BaseModel):
    username: constr(strip_whitespace=True, min_length=3, max_length=32)
    public_key: str
    encrypted_private_key: str
    blockchain_network: constr(strip_whitespace=True, min_length=1)

class UserCreateSchema(BaseModel):
    firebase_uid: constr(strip_whitespace=True, min_length=1)
    email: constr(strip_whitespace=True, min_length=5)
    username: constr(strip_whitespace=True, min_length=3, max_length=32)


# --- Routes ---

# --- THIS IS THE MISSING ENDPOINT ---
@user_api_bp.route("/users/username-check/<username>", methods=["GET"])
def username_check(username):
    """Checks if a username is already taken."""
    try:
        # Query the database to see if a user with this username exists
        user_exists = db.session.query(UserAccount).filter_by(username=username).first()
        
        # If user_exists is None, the username is available
        is_available = not user_exists
        
        return jsonify(available=is_available), http.HTTPStatus.OK
        
    except Exception as e:
        logger.error(f"Error checking username '{username}': {e}", exc_info=True)
        return jsonify(error="An internal server error occurred."), http.HTTPStatus.INTERNAL_SERVER_ERROR


@user_api_bp.route("/profile", methods=["GET"])
@require_firebase_token
def get_user_profile():
    """Returns the authenticated user's profile information including wallets."""
    user = g.user
    if not user:
        return jsonify(error="User not authenticated or found"), http.HTTPStatus.UNAUTHORIZED

    try:
        # Use our enhanced to_dict to include wallets
        return jsonify(user.to_dict(include_wallets=True)), http.HTTPStatus.OK
    except Exception as e:
        logger.exception(f"Error serializing user profile: {e}")
        return jsonify(error="Failed to load profile"), http.HTTPStatus.INTERNAL_SERVER_ERROR


@user_api_bp.route("/users/register-wallet", methods=["POST"])
@require_firebase_token
def register_user_wallet():
    """
    Register a new UserAccount and associated UserWallet.
    Firebase auth required.
    """
    firebase_user = g.firebase_user
    logger.info(f"Registering wallet for Firebase UID: {firebase_user.get('uid')}")

    try:
        payload = request.get_json()
        if not payload:
            return jsonify(error="Missing JSON body"), http.HTTPStatus.BAD_REQUEST

        validated_data = WalletRegistrationSchema(**payload)

        if firebase_user.get('email') is None:
            return jsonify(error="Firebase user email is required"), http.HTTPStatus.BAD_REQUEST

        # Check if user already exists by email or firebase_uid
        existing_user = db.session.query(UserAccount).filter(
            (UserAccount.email == firebase_user['email']) | (UserAccount.firebase_uid == firebase_user['uid'])
        ).first()
        if existing_user:
            return jsonify(error="User with this email or Firebase UID already exists."), http.HTTPStatus.CONFLICT

        # Check if wallet public address already exists
        existing_wallet = db.session.query(UserWallet).filter_by(public_address=validated_data.public_key).first()
        if existing_wallet:
            return jsonify(error="Wallet address already registered."), http.HTTPStatus.CONFLICT

        new_user = UserAccount(
            firebase_uid=firebase_user['uid'],
            email=firebase_user['email'],
            username=validated_data.username
        )
        db.session.add(new_user)
        db.session.flush()

        new_wallet = UserWallet(
            user_id=new_user.id,
            public_address=validated_data.public_key,
            encrypted_private_key=validated_data.encrypted_private_key,
            blockchain_network=validated_data.blockchain_network,
            is_primary=True
        )
        db.session.add(new_wallet)
        db.session.commit()

        logger.info(f"User '{validated_data.username}' registered successfully with ID: {new_user.id}")
        return jsonify({
            "message": "User and wallet created successfully",
            "userId": str(new_user.id)
        }), http.HTTPStatus.CREATED

    except ValidationError as ve:
        logger.warning(f"Validation failed: {ve.errors()}")
        return jsonify(error="Invalid input", details=ve.errors()), http.HTTPStatus.UNPROCESSABLE_ENTITY

    except IntegrityError as e:
        db.session.rollback()
        logger.warning(f"Integrity error (duplicate): {e}")
        return jsonify(error="User with this email, UID, or wallet address already exists."), http.HTTPStatus.CONFLICT

    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error during registration: {e}", exc_info=True)
        return jsonify(error="An internal server error occurred."), http.HTTPStatus.INTERNAL_SERVER_ERROR


@user_api_bp.route("/users", methods=["POST"])
@require_firebase_token
def create_user():
    """
    Endpoint to create a new user.
    Redirects to register-wallet endpoint logic.
    """
    # This is a simple proxy; you might want more distinct logic later.
    return register_user_wallet()
