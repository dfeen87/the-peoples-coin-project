import http
import logging
from flask import Blueprint, request, jsonify, g
from pydantic import BaseModel, ValidationError, constr
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

from peoples_coin.utils.recaptcha import verify_recaptcha
from peoples_coin.extensions import db
from peoples_coin.utils.auth import require_firebase_token
from peoples_coin.models import UserAccount, UserWallet
from peoples_coin.models.db_utils import get_session_scope

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

@user_api_bp.route("/users/username-check/<username>", methods=["GET"])
def username_check(username):
    logger.info(f"Checking availability for username: {username}")
    try:
        with get_session_scope() as session:
            user_exists = session.query(UserAccount).filter(
                func.lower(UserAccount.username) == username.lower()
            ).first()

            is_available = not user_exists
            return jsonify(available=is_available), http.HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error checking username '{username}': {e}", exc_info=True)
        return jsonify(error="An internal server error occurred."), http.HTTPStatus.INTERNAL_SERVER_ERROR


@user_api_bp.route("/profile", methods=["GET"])
@require_firebase_token
def get_user_profile():
    user = g.user
    if not user:
        return jsonify(error="User not authenticated or found"), http.HTTPStatus.UNAUTHORIZED

    try:
        return jsonify(user.to_dict(include_wallets=True)), http.HTTPStatus.OK
    except Exception as e:
        logger.exception(f"Error serializing user profile: {e}")
        return jsonify(error="Failed to load profile"), http.HTTPStatus.INTERNAL_SERVER_ERROR


@user_api_bp.route("/users/register-wallet", methods=["POST"])
@require_firebase_token
def create_user_and_wallet():
    firebase_user = g.firebase_user
    logger.info(f"Creating user and wallet for Firebase UID: {firebase_user.get('uid')}")

    try:
        payload = request.get_json()
        if not payload:
            return jsonify(error="Missing JSON body"), http.HTTPStatus.BAD_REQUEST

        # Extract reCAPTCHA token from request JSON
        recaptcha_token = payload.get("recaptcha_token")
        if not recaptcha_token:
            return jsonify(error="Missing reCAPTCHA token"), http.HTTPStatus.BAD_REQUEST

        # Get user IP and User-Agent for verification context
        user_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        user_agent = request.headers.get("User-Agent", "")

        # Verify reCAPTCHA token - action name matches this endpoint
        valid, message = verify_recaptcha(
            token=recaptcha_token,
            action="create_user_and_wallet",
            user_ip=user_ip,
            user_agent=user_agent,
        )
        if not valid:
            return jsonify(error="reCAPTCHA validation failed", details=message), http.HTTPStatus.BAD_REQUEST

        # Proceed with wallet registration as before
        validated_data = WalletRegistrationSchema(**payload)

        if not firebase_user.get('email'):
            return jsonify(error="Firebase user email is required"), http.HTTPStatus.BAD_REQUEST

        with get_session_scope() as session:
            existing_user = session.query(UserAccount).filter(
                (func.lower(UserAccount.email) == firebase_user['email'].lower()) |
                (UserAccount.firebase_uid == firebase_user['uid'])
            ).first()
            if existing_user:
                return jsonify(error="User with this email or Firebase UID already exists."), http.HTTPStatus.CONFLICT

            existing_wallet = session.query(UserWallet).filter(
                func.lower(UserWallet.public_address) == validated_data.public_key.lower()
            ).first()
            if existing_wallet:
                return jsonify(error="Wallet address already registered."), http.HTTPStatus.CONFLICT

            new_user = UserAccount(
                firebase_uid=firebase_user['uid'],
                email=firebase_user['email'],
                username=validated_data.username
            )
            session.add(new_user)
            session.flush()  # get new_user.id before commit

            new_wallet = UserWallet(
                user_id=new_user.id,
                public_address=validated_data.public_key,
                encrypted_private_key=validated_data.encrypted_private_key,
                blockchain_network=validated_data.blockchain_network,
                is_primary=True
            )
            session.add(new_wallet)
            session.commit()

            logger.info(f"User '{validated_data.username}' registered successfully with ID: {new_user.id}")
            return jsonify({
                "message": "User and wallet created successfully",
                "userId": str(new_user.id)
            }), http.HTTPStatus.CREATED

    except ValidationError as ve:
        logger.warning(f"Validation failed: {ve.errors()}")
        return jsonify(error="Invalid input", details=ve.errors()), http.HTTPStatus.UNPROCESSABLE_ENTITY

    except IntegrityError as e:
        logger.warning(f"Integrity error (duplicate): {e}")
        return jsonify(error="User with this email, UID, or wallet address already exists."), http.HTTPStatus.CONFLICT

    except Exception as e:
        logger.error(f"Unexpected error during registration: {e}", exc_info=True)
        return jsonify(error="An internal server error occurred."), http.HTTPStatus.INTERNAL_SERVER_ERROR


@user_api_bp.route("/users", methods=["POST"])
@require_firebase_token
def create_user():
    """
    Unified user creation endpoint.
    Proxies to create_user_and_wallet for now.
    """
    # If you want a separate action for reCAPTCHA, adjust here
    return create_user_and_wallet()

