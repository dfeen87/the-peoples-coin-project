# peoples_coin/routes/user_api_routes.py
import http
import logging
from flask import Blueprint, request, jsonify, g
from sqlalchemy import func
from pydantic import ValidationError
from firebase_admin import auth as firebase_auth

from peoples_coin.extensions import db
from peoples_coin.utils.auth import require_firebase_token
# CORRECTED: Import from the central models package
from peoples_coin.models import UserAccount, UserWallet
from peoples_coin.models.db_utils import get_session_scope
from .schemas import WalletRegistrationSchema # Assuming schemas are in routes/schemas.py

logger = logging.getLogger(__name__)
user_api_bp = Blueprint("user_api", __name__, url_prefix="/api/users")

@user_api_bp.route("/check-username/<username>", methods=["GET"])
def username_check(username):
    """Checks if a username is available."""
    with get_session_scope() as session:
        exists = session.query(UserAccount).filter(func.lower(UserAccount.username) == username.lower()).first() is not None
        return jsonify(available=not exists), http.HTTPStatus.OK

@user_api_bp.route("/me", methods=["GET"])
@require_firebase_token
def get_current_user():
    """Returns authenticated user's profile. Creates DB record if missing."""
    firebase_user_info = g.user  # g.user is the FirebaseUser object set by @require_firebase_token
    with get_session_scope() as session:
        user = session.query(UserAccount).filter_by(firebase_uid=firebase_user_info.firebase_uid).first()
        if not user:
            user = UserAccount(
                firebase_uid=firebase_user_info.firebase_uid,
                email=firebase_user_info.email,
                username=firebase_user_info.username or (firebase_user_info.email.split('@')[0] if firebase_user_info.email else None)
            )
            session.add(user)
            logger.info(f"Auto-created user record for Firebase UID: {user.firebase_uid}")
        return jsonify(user.to_dict(include_wallets=True)), http.HTTPStatus.OK

@user_api_bp.route("/register-wallet", methods=["POST"])
@require_firebase_token
def create_user_and_wallet():
    """Creates user profile details and initial wallet after Firebase sign-up."""
    try:
        payload = request.get_json()
        if not payload: return jsonify(error="Missing JSON body"), http.HTTPStatus.BAD_REQUEST
        
        validated_data = WalletRegistrationSchema(**payload)
        user = g.user # from @require_firebase_token

        with get_session_scope() as session:
            if session.query(UserAccount).filter(func.lower(UserAccount.username) == validated_data.username.lower()).first():
                return jsonify(error="username_taken"), http.HTTPStatus.CONFLICT
            if session.query(UserWallet).filter(func.lower(UserWallet.public_address) == validated_data.public_key.lower()).first():
                return jsonify(error="Wallet address already registered."), http.HTTPStatus.CONFLICT
            
            user.username = validated_data.username
            session.add(user)
            session.flush()

            new_wallet = UserWallet(
                user_id=user.id,
                public_address=validated_data.public_key,
                encrypted_private_key=validated_data.encrypted_private_key,
                blockchain_network=validated_data.blockchain_network,
                is_primary=True
            )
            session.add(new_wallet)
            logger.info(f"User '{user.username}' registered wallet successfully.")
            return jsonify({"message": "User and wallet created successfully", "userId": str(user.id)}), http.HTTPStatus.CREATED

    except ValidationError as ve:
        return jsonify(error="Invalid input", details=ve.errors()), http.HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception:
        logger.exception("Unexpected error during wallet registration.")
        return jsonify(error="An internal server error occurred."), http.HTTPStatus.INTERNAL_SERVER_ERROR

@user_api_bp.route("/profile", methods=["DELETE"])
@require_firebase_token
def delete_user_account():
    """Deletes the authenticated user's account from Firebase and the database."""
    firebase_user = g.user  # g.user is the FirebaseUser object set by @require_firebase_token
    try:
        firebase_auth.delete_user(firebase_user.firebase_uid)
        with get_session_scope() as session:
            # Find the user in the database by their Firebase UID
            db_user = session.query(UserAccount).filter(
                UserAccount.firebase_uid == firebase_user.firebase_uid
            ).first()
            if db_user:
                # The ON DELETE CASCADE in the schema handles deleting related items like wallets
                session.delete(db_user)
                logger.info(f"Deleted user from Firebase and DB: {db_user.id}")
        return jsonify(message="Account deleted successfully."), http.HTTPStatus.OK
    except Exception:
        logger.exception("Error during account deletion.")
        return jsonify(error="An internal server error occurred."), http.HTTPStatus.INTERNAL_SERVER_ERROR
