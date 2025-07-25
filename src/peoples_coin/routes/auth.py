import http
import secrets
from flask import Blueprint, request, jsonify, current_app
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import ApiKey, UserAccount
from peoples_coin.extensions import db
from werkzeug.security import check_password_hash

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

