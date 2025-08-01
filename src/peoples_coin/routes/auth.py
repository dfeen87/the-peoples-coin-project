import http
import secrets
from functools import wraps
from flask import Blueprint, request, jsonify, current_app, g
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import ApiKey, UserAccount
from peoples_coin.extensions import db
from werkzeug.security import check_password_hash
# We need this import to use the token validation decorator from your utils
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

        # Check password hash (assuming your UserAccount stores hashed password)
        if not user.password_hash or not check_password_hash(user.password_hash, password):
            return jsonify({KEY_ERROR: "Invalid email or password"}), http.HTTPStatus.UNAUTHORIZED

        # Return user info (exclude sensitive info)
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


# This is the new endpoint you need to add to fix the issue.
@auth_bp.route("/users/me", methods=["GET"])
@require_firebase_token
def get_current_user():
    """
    Retrieves the current authenticated user's profile and card information.
    This endpoint is protected by a Firebase token.
    """
    try:
        # The 'require_firebase_token' decorator is assumed to authenticate the user
        # and attach the user's information (like user_id) to the Flask 'g' object.
        user_id = g.user_id

        if not user_id:
            return jsonify({KEY_ERROR: "User ID not found in token"}), http.HTTPStatus.UNAUTHORIZED

        with get_session_scope(db) as session:
            # Fetch the user from the database. We use the 'UserAccount' model you already have.
            user = session.query(UserAccount).filter_by(id=user_id).first()

            if user is None:
                return jsonify({KEY_ERROR: "User not found"}), http.HTTPStatus.NOT_FOUND

            # Assuming your UserAccount model has a relationship to a 'cards' collection/list.
            # You may need to adjust this part based on your actual model.
            cards = [
                {"id": str(card.id), "type": card.card_type, "last4": card.last_four}
                for card in user.cards
            ] if hasattr(user, 'cards') else []

            # Prepare the user data to be sent as a JSON response.
            # This will fix the issue of not fetching user name and account information.
            user_profile = {
                "id": str(user.id),
                "name": user.username,  # Adjust field name if 'name' is different
                "email": user.email,
                "balance": str(user.balance),
                "goodwill_coins": user.goodwill_coins,
                "cards": cards
            }

            return jsonify(user_profile), http.HTTPStatus.OK

    except Exception as e:
        # Log the error for debugging purposes in case something goes wrong
        current_app.logger.error(f"Error fetching user profile: {e}")
        return jsonify({KEY_ERROR: "An internal server error occurred"}), http.HTTPStatus.INTERNAL_SERVER_ERROR
