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
user_api_bp = Blueprint("user_api", __name__)

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
        exists = db.session.query(UserAccount).filter(
            UserAccount.username.ilike(username)
        ).first()
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

        new_user = UserAccount(
            firebase_uid=firebase_user['uid'],
            email=firebase_user['email'],
            username=validated_data.username
        )
        db.session.add(new_user)
        db.session.flush()  # Obtain UUID from DB

        new_wallet = UserWallet(
            user_id=new_user.id,
            public_address=validated_data.public_key,
            encrypted_private_key=validated_data.encrypted_private_key,
            is_primary=True
        )
        db.session.add(new_wallet)
        db.session.commit()

        logger.info(f"User '{validated_data.username}' registered successfully.")
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
        return jsonify(error="User with this email, UID, or username already exists."), http.HTTPStatus.CONFLICT

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
    return jsonify(user.to_dict()), http.HTTPStatus.OK

