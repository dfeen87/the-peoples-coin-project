import http
import logging
from functools import wraps

from flask import Blueprint, request, jsonify, g
from flask_cors import CORS
from pydantic import BaseModel, ValidationError, constr
from sqlalchemy.exc import IntegrityError, OperationalError

from peoples_coin.extensions import db
from peoples_coin.utils.auth import require_firebase_token
from peoples_coin.models import UserAccount, UserWallet

logger = logging.getLogger(__name__)

# --- Blueprint Setup ---
user_api_bp = Blueprint("user_api", __name__)

# --- CORS Configuration ---
CORS(
    user_api_bp,
    resources={r"/*": {"origins": ["https://brightacts.com", "http://localhost:3000"]}},
    supports_credentials=True,
)

# --- Pydantic Schemas ---

class WalletRegistrationSchema(BaseModel):
    username: constr(strip_whitespace=True, min_length=3, max_length=32)
    public_key: str
    encrypted_private_key: str
    blockchain_network: constr(strip_whitespace=True, min_length=1)  # added if you want this field

class UserCreateSchema(BaseModel):
    firebase_uid: constr(strip_whitespace=True, min_length=1)
    email: constr(strip_whitespace=True, min_length=5)
    username: constr(strip_whitespace=True, min_length=3, max_length=32)

# --- Routes ---

@user_api_bp.route("/profile", methods=["GET", "OPTIONS"])
@require_firebase_token
def get_user_profile():
    """Returns the authenticated user's profile information including wallets."""
    if request.method == "OPTIONS":
        return jsonify({}), http.HTTPStatus.OK

    user = g.user
    if not user:
        return jsonify(error="User not authenticated or found"), http.HTTPStatus.UNAUTHORIZED

    try:
        # Use our enhanced to_dict to include wallets
        return jsonify(user.to_dict(include_wallets=True)), http.HTTPStatus.OK
    except Exception as e:
        logger.exception(f"Error serializing user profile: {e}")
        return jsonify(error="Failed to load profile"), http.HTTPStatus.INTERNAL_SERVER_ERROR


@user_api_bp.route("/users/register-wallet", methods=["POST", "OPTIONS"])
@require_firebase_token
def register_user_wallet():
    """
    Register a new UserAccount and associated UserWallet.
    Firebase auth required.
    """
    if request.method == "OPTIONS":
        return jsonify({}), 200

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
        existing_user_by_email = db.session.query(UserAccount).filter_by(email=firebase_user['email']).first()
        if existing_user_by_email:
            return jsonify(error="User with this email already exists."), http.HTTPStatus.CONFLICT

        existing_user_by_uid = db.session.query(UserAccount).filter_by(firebase_uid=firebase_user['uid']).first()
        if existing_user_by_uid:
            return jsonify(error="User with this Firebase UID already exists."), http.HTTPStatus.CONFLICT

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
        db.session.flush()  # flush to get new_user.id

        new_wallet = UserWallet(
            user_id=new_user.id,
            public_address=validated_data.public_key,
            encrypted_private_key=validated_data.encrypted_private_key,
            blockchain_network=validated_data.blockchain_network,  # assuming your model has this
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


@user_api_bp.route("/users", methods=["POST", "OPTIONS"])
@require_firebase_token
def create_user():
    """
    Endpoint to create a new user.
    Redirects to register-wallet endpoint logic.
    """
    if request.method == "OPTIONS":
        return jsonify({}), 200

    # Proxy to register_user_wallet for now
    return register_user_wallet()


@user_api_bp.route("/profile", methods=["GET", "OPTIONS"])
@require_firebase_token
def get_user_profile():
    """Returns the authenticated user's profile information including wallets."""
    if request.method == "OPTIONS":
        return jsonify({}), 200

    user = g.user
    if not user:
        return jsonify(error="User not authenticated or found"), http.HTTPStatus.UNAUTHORIZED

    wallets = db.session.query(UserWallet).filter_by(user_id=user.id).all()
    user_data = user.to_dict()
    user_data['wallets'] = [wallet.to_dict() for wallet in wallets]

    return jsonify(user_data), http.HTTPStatus.OK


# --- Helper to register blueprint ---

def register_routes(app):
    app.register_blueprint(user_api_bp, url_prefix="/api")

