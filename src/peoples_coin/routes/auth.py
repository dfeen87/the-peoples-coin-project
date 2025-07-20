import http
import secrets
from flask import Blueprint, request, jsonify
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import ApiKey, UserAccount
from peoples_coin.extensions import db

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

