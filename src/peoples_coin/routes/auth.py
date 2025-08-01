import http
import secrets
from flask import Blueprint, request, jsonify, current_app, g
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import ApiKey, UserAccount
from peoples_coin.extensions import db
from werkzeug.security import check_password_hash
from peoples_coin.utils.auth import require_firebase_token

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

KEY_ERROR = "error"
KEY_MESSAGE = "message"


@auth_bp.route("/create-api-key", methods=["POST"])
def create_api_key():
    if not request.is_json:
        return jsonify({KEY_ERROR: "Content-Type must be application/json"}), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    data = request.get_json()
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({KEY_ERROR: "Missing 'user_id' in request body"}), http.HTTPStatus.BAD_REQUEST

    with get_session_scope(db) as session:
        user = session.query(UserAccount).filter_by(id=user_id).first()
        if not user:
            return jsonify({KEY_ERROR: f"User with user_id '{user_id}' not found"}), http.HTTPStatus.NOT_FOUND

        new_key = secrets.token_urlsafe(30)
        api_key_obj = ApiKey(key=new_key, user_id=user.id)
        session.add(api_key_obj)
        session.flush()

        return jsonify({
            KEY_MESSAGE: "API key created successfully",
            "api_key": new_key
        }), http.HTTPStatus.CREATED


@auth_bp.route("/signin", methods=["POST"])
def signin():
    if not request.is_json:
        return jsonify({KEY_ERROR: "Content-Type must be application/json"}), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({KEY_ERROR: "Email and password are required"}), http.HTTPStatus.BAD_REQUEST

    with get_session_scope(db) as session:
        user = session.query(UserAccount).filter_by(email=email).first()
        if not user:
            return jsonify({KEY_ERROR: "Invalid email or password"}), http.HTTPStatus.UNAUTHORIZED

        if not user.password_hash or not check_password_hash(user.password_hash, password):
            return jsonify({KEY_ERROR: "Invalid email or password"}), http.HTTPStatus.UNAUTHORIZED

        user_info = {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "balance": str(user.balance),
            "goodwill_coins": user.goodwill_coins,
        }

        return jsonify({
            KEY_MESSAGE: "Sign-in successful",
            "user": user_info
        }), http.HTTPStatus.OK


def serialize_user(user):
    """
    Helper function to serialize user object to JSON-compatible dict.
    """
    cards = [
        {"id": str(card.id), "type": card.card_type, "last4": card.last_four}
        for card in getattr(user, 'cards', [])
    ]

    return {
        "id": str(user.id),
        "name": user.username,
        "email": user.email,
        "balance": str(user.balance),
        "goodwill_coins": user.goodwill_coins,
        "cards": cards
    }


@auth_bp.route("/users/me", methods=["GET"])
@require_firebase_token
def get_current_user():
    """
    Retrieves the current authenticated user's profile.
    Auto-creates the user in DB if not found.
    """
    try:
        user_id = g.user_id  # Firebase UID from token
        user_email = getattr(g, "user_email", None)
        user_name = getattr(g, "user_name", None) or (user_email.split("@")[0] if user_email else None)

        if not user_id:
            return jsonify({KEY_ERROR: "User ID not found in token"}), http.HTTPStatus.UNAUTHORIZED

        with get_session_scope(db) as session:
            user = session.query(UserAccount).filter_by(id=user_id).first()

            if not user:
                # Create new user if not exists
                user = UserAccount(
                    id=user_id,
                    email=user_email,
                    username=user_name,
                    balance=0,
                    goodwill_coins=0
                )
                session.add(user)
                session.flush()

            return jsonify(serialize_user(user)), http.HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error fetching or creating user profile: {e}")
        return jsonify({KEY_ERROR: "An internal server error occurred"}), http.HTTPStatus.INTERNAL_SERVER_ERROR


@auth_bp.route("/users/<user_id>", methods=["GET"])
@require_firebase_token
def get_user_by_id(user_id):
    """
    Fetch user profile by user_id.
    """
    try:
        with get_session_scope(db) as session:
            user = session.query(UserAccount).filter_by(id=user_id).first()
            if not user:
                return jsonify({KEY_ERROR: "User not found"}), http.HTTPStatus.NOT_FOUND

            return jsonify(serialize_user(user)), http.HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error fetching user by ID: {e}")
        return jsonify({KEY_ERROR: "An internal server error occurred"}), http.HTTPStatus.INTERNAL_SERVER_ERROR

