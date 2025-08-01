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
            g.user = key_record.user
            session.commit()

        return f(*args, **kwargs)
    return decorated


def require_firebase_token(f):
    """Decorator to protect routes with a Firebase ID token and auto-create DB user if needed."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({KEY_ERROR: "Missing or invalid Authorization header"}), http.HTTPStatus.UNAUTHORIZED
        
        id_token = auth_header.split("Bearer ")[1]

        try:
            decoded_token = auth.verify_id_token(id_token)
            uid = decoded_token['uid']
            email = decoded_token.get('email')
            name = decoded_token.get('name') or (email.split('@')[0] if email else None)

            with get_session_scope(db) as session:
                user = session.query(UserAccount).filter_by(firebase_uid=uid).first()
                
                # Auto-create user if not found
                if not user:
                    logger.info(f"No user found for UID {uid}, creating new account.")
                    user = UserAccount(
                        firebase_uid=uid,
                        email=email,
                        username=name,
                        balance=0,
                        goodwill_coins=0
                    )
                    session.add(user)
                    session.flush()
                    logger.info(f"Created new user {user.id} for Firebase UID {uid}")

                g.user = user

        except Exception as e:
            logger.error(f"Error verifying Firebase token: {e}")
            return jsonify({KEY_ERROR: "Invalid, expired, or revoked token"}), http.HTTPStatus.UNAUTHORIZED

        return f(*args, **kwargs)
    return decorated

