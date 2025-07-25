# src/peoples_coin/utils/auth.py
import http
import logging
from functools import wraps
from datetime import datetime, timezone

from flask import request, jsonify, g
import firebase_admin
from firebase_admin import auth

from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import ApiKey, UserAccount
from peoples_coin.extensions import db

KEY_ERROR = "error"
logger = logging.getLogger(__name__)

def require_api_key(f):
    """Decorator to protect routes with a database-backed API key."""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key_str = request.headers.get("X-API-KEY")
        if not api_key_str:
            return jsonify({KEY_ERROR: "Missing API key"}), http.HTTPStatus.UNAUTHORIZED

        with get_session_scope(db) as session:
            key_record = session.query(ApiKey).filter(
                ApiKey.key == api_key_str,
                (ApiKey.expires_at > datetime.now(timezone.utc)) | (ApiKey.expires_at == None)
            ).first()

            if not key_record:
                return jsonify({KEY_ERROR: "Invalid or expired API key"}), http.HTTPStatus.UNAUTHORIZED

            key_record.last_used_at = datetime.now(timezone.utc)
            g.user = key_record.user # Assumes relationship from ApiKey -> UserAccount
            session.commit()

        return f(*args, **kwargs)
    return decorated

def require_firebase_token(f):
    """Decorator to protect routes with a Firebase ID token and load the application user."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({KEY_ERROR: "Missing or invalid Authorization header"}), http.HTTPStatus.UNAUTHORIZED
        
        id_token = auth_header.split("Bearer ")[1]

        try:
            decoded_token = auth.verify_id_token(id_token)
            uid = decoded_token['uid']

            with get_session_scope(db) as session:
                user = session.query(UserAccount).filter_by(firebase_uid=uid).first()
                if not user:
                    return jsonify({KEY_ERROR: "User profile not found"}), http.HTTPStatus.FORBIDDEN
                g.user = user

        except auth.AuthError as e:
            logger.warning(f"Firebase token verification failed: {e}")
            return jsonify({KEY_ERROR: "Invalid, expired, or revoked token"}), http.HTTPStatus.UNAUTHORIZED
        except Exception as e:
            logger.error(f"An unexpected error occurred during token verification: {e}")
            return jsonify({KEY_ERROR: "Could not process authentication token"}), http.HTTPStatus.INTERNAL_SERVER_ERROR

        return f(*args, **kwargs)
    return decorated
