# src/peoples_coin/utils/auth.py
import http
import logging
from functools import wraps
from flask import request, jsonify, g
from firebase_admin import auth

logger = logging.getLogger(__name__)
KEY_ERROR = "error"

class FirebaseUser:
    """Lightweight object to hold Firebase-authenticated user info."""
    def __init__(self, uid, email=None, username=None):
        self.firebase_uid = uid
        self.email = email
        self.username = username

def require_firebase_token(f):
    """Decorator to protect routes with a Firebase ID token."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({KEY_ERROR: "Missing or invalid Authorization header"}), http.HTTPStatus.UNAUTHORIZED

        id_token = auth_header.split("Bearer ")[1]

        try:
            decoded_token = auth.verify_id_token(id_token)
            uid = decoded_token.get("uid")
            email = decoded_token.get("email")
            display_name = decoded_token.get("name")

            if not uid:
                return jsonify({KEY_ERROR: "Invalid token: no UID"}), http.HTTPStatus.UNAUTHORIZED

            # Attach FirebaseUser object directly to g.user
            g.user = FirebaseUser(
                uid=uid,
                email=email,
                username=display_name or (email.split("@")[0] if email else None)
            )

        except Exception as e:
            logger.error(f"Firebase token verification failed: {e}")
            return jsonify({KEY_ERROR: "Invalid, expired, or revoked token"}), http.HTTPStatus.UNAUTHORIZED

        return f(*args, **kwargs)
    return decorated

