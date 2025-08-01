# src/peoples_coin/routes/auth.py
import http
from flask import Blueprint, request, jsonify, g
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import ApiKey, UserAccount
from peoples_coin.extensions import db
from peoples_coin.utils.auth import require_firebase_token

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")
KEY_ERROR = "error"
KEY_MESSAGE = "message"


@auth_bp.route("/users/me", methods=["GET"])
@require_firebase_token
def get_current_user():
    """Return the currently authenticated user's profile."""
    user = g.user
    if not user:
        return jsonify({KEY_ERROR: "User not found"}), http.HTTPStatus.NOT_FOUND

    user_profile = {
        "id": str(user.id),
        "name": user.username,
        "email": user.email,
        "balance": str(user.balance),
        "goodwill_coins": user.goodwill_coins,
    }
    return jsonify(user_profile), http.HTTPStatus.OK


@auth_bp.route("/users/<firebase_uid>", methods=["GET"])
def get_user_by_uid(firebase_uid):
    """Get a user by Firebase UID, auto-create if missing."""
    with get_session_scope(db) as session:
        user = session.query(UserAccount).filter_by(firebase_uid=firebase_uid).first()

        if not user:
            # Create a minimal placeholder user
            user = UserAccount(
                firebase_uid=firebase_uid,
                email=None,
                username=None,
                balance=0,
                goodwill_coins=0
            )
            session.add(user)
            session.flush()

        user_profile = {
            "id": str(user.id),
            "name": user.username,
            "email": user.email,
            "balance": str(user.balance),
            "goodwill_coins": user.goodwill_coins,
        }
        return jsonify(user_profile), http.HTTPStatus.OK

