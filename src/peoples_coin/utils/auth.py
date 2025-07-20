from functools import wraps
from flask import request, jsonify
import http
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import ApiKey
from peoples_coin.extensions import db

KEY_ERROR = "error"

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-KEY")
        if not api_key:
            return jsonify({KEY_ERROR: "Missing API key"}), http.HTTPStatus.UNAUTHORIZED

        with get_session_scope(db) as session:
            key_record = session.query(ApiKey).filter_by(key=api_key, revoked=False).first()
            if not key_record:
                return jsonify({KEY_ERROR: "Invalid or revoked API key"}), http.HTTPStatus.UNAUTHORIZED

        return f(*args, **kwargs)
    return decorated

