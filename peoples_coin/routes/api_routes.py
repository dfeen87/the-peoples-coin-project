import http
import logging
from flask import Blueprint, request, jsonify, g
from pydantic import BaseModel, ValidationError, constr
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

# Added for the account deletion functionality
from firebase_admin import auth as firebase_auth

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

@user_api_bp.route("/users/check-username/<username>", methods=["GET"])
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


# New DELETE endpoint to delete the user account from both systems
@user_api_bp.route("/profile", methods=["DELETE"])
@require_firebase_token
def delete_user_account():
    firebase_user = g.user  # g.user is the FirebaseUser object set by @require_firebase_token
    if not firebase_user:
        return jsonify(error="User not found."), http.HTTPStatus.NOT_FOUND

    try:
        # 1. Delete user from Firebase
        firebase_auth.delete_user(firebase_user.firebase_uid)
        logger.info(f"Deleted user from Firebase: {firebase_user.firebase_uid}")

        # 2. Delete user and their wallets from our database
        with get_session_scope() as session:
            # Find the user in the database by their Firebase UID
            db_user = session.query(UserAccount).filter(
                UserAccount.firebase_uid == firebase_user.firebase_uid
            ).first()
            if db_user:
                session.query(UserWallet).filter(UserWallet.user_id == db_user.id).delete()
                session.query(UserAccount).filter(UserAccount.id == db_user.id).delete()
                session.commit()
                logger.info(f"Deleted user from database: {db_user.username}")

        return jsonify(message="Account deleted successfully."), http.HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error during account deletion: {e}", exc_info=True)
        return jsonify(error="An internal server error occurred."), http.HTTPStatus.INTERNAL_SERVER_ERROR


@user_api_bp.route("/users/register-wallet", methods=["POST"])
@require_firebase_token
def create_user_and_wallet():
    firebase_user = g.user  # g.user is the FirebaseUser object set by @require_firebase_token
    logger.info(f"Creating user and wallet for Firebase UID: {firebase_user.firebase_uid}")

    try:
        payload = request.get_json()
        if not payload:
            return jsonify(error="Missing JSON body"), http.HTTPStatus.BAD_REQUEST

        # --- reCAPTCHA validation remains the same ---
        recaptcha_token = payload.get("recaptcha_token")
        if not recaptcha_token:
            return jsonify(error="Missing reCAPTCHA token"), http.HTTPStatus.BAD_REQUEST

        user_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        user_agent = request.headers.get("User-Agent", "")

        valid, message = verify_recaptcha(
            token=recaptcha_token,
            action="create_user_and_wallet",
            user_ip=user_ip,
            user_agent=user_agent,
        )
        if not valid:
            return jsonify(error="reCAPTCHA validation failed", details=message), http.HTTPStatus.BAD_REQUEST

        validated_data = WalletRegistrationSchema(**payload)

        if not firebase_user.email:
            return jsonify(error="Firebase user email is required"), http.HTTPStatus.BAD_REQUEST

        with get_session_scope() as session:
            # --- START: MODIFIED SECTION ---

            # 1. Final, authoritative check for the USERNAME. This is the fix.
            existing_username = session.query(UserAccount).filter(
                func.lower(UserAccount.username) == validated_data.username.lower()
            ).first()
            if existing_username:
                # Return a specific error your client can handle
                return jsonify(error="username_taken"), http.HTTPStatus.CONFLICT

            # 2. Check for existing Firebase UID or email (this was already correct)
            existing_user = session.query(UserAccount).filter(
                (func.lower(UserAccount.email) == firebase_user.email.lower()) |
                (UserAccount.firebase_uid == firebase_user.firebase_uid)
            ).first()
            if existing_user:
                return jsonify(error="User with this email or Firebase UID already exists."), http.HTTPStatus.CONFLICT
            
            # --- END: MODIFIED SECTION ---

            # Wallet check remains the same
            existing_wallet = session.query(UserWallet).filter(
                func.lower(UserWallet.public_address) == validated_data.public_key.lower()
            ).first()
            if existing_wallet:
                return jsonify(error="Wallet address already registered."), http.HTTPStatus.CONFLICT

            new_user = UserAccount(
                firebase_uid=firebase_user.firebase_uid,
                email=firebase_user.email,
                username=validated_data.username
            )
            session.add(new_user)
            # Use flush to get the new_user.id before committing
            session.flush()

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
        # This is your safety net if the check above fails due to a race condition.
        # It's good practice to check the error content to be more specific.
        if 'username' in str(e.orig).lower():
            return jsonify(error="username_taken"), http.HTTPStatus.CONFLICT
        return jsonify(error="A user with these details already exists."), http.HTTPStatus.CONFLICT

    except Exception as e:
        logger.error(f"Unexpected error during registration: {e}", exc_info=True)
        return jsonify(error="An internal server error occurred."), http.HTTPStatus.INTERNAL_SERVER_ERROR

# This can be a simplified alias
@user_api_bp.route("/users", methods=["POST"])
@require_firebase_token
def create_user():
    return create_user_and_wallet()

@user_api_bp.route("/users/<user_id>", methods=["GET"])
@require_firebase_token
def get_user_by_id(user_id):
    # This route logic seems to be trying to get a user profile, 
    # but uses the authenticated user 'g.user' instead of 'user_id' from the URL.
    # It works, but might be slightly confusing. No changes needed for the fix.
    user = g.user
    if not user:
        return jsonify(error="User not authenticated or found"), http.HTTPStatus.UNAUTHORIZED

    try:
        # This check is good, it ensures users can only see their own profile.
        if str(user.id) != user_id:
             return jsonify(error="Unauthorized access to user profile"), http.HTTPStatus.FORBIDDEN
             
        return jsonify(user.to_dict(include_wallets=True)), http.HTTPStatus.OK
    except Exception as e:
        logger.exception(f"Error serializing user profile for ID '{user_id}': {e}")
        return jsonify(error="Failed to load profile"), http.HTTPStatus.INTERNAL_SERVER_ERROR
