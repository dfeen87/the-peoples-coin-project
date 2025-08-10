# peoples_coin/systems/auth_system.py
import logging
import time
from functools import wraps
from flask import request, jsonify, current_app, g
from werkzeug.security import generate_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from peoples_coin.models import UserAccount
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.utils.email import send_email # Assuming this utility exists

logger = logging.getLogger(__name__)

# ===========================
# Token Serializer Utilities
# ===========================
def get_serializer(secret_key=None):
    """Creates a timed serializer for generating and verifying tokens."""
    secret_key = secret_key or current_app.config.get("SECRET_KEY")
    if not secret_key:
        raise ValueError("SECRET_KEY is not configured.")
    return URLSafeTimedSerializer(secret_key)

def generate_token(data: dict, salt: str, expires_in_sec=3600):
    """Generates a secure, timed, and salted token."""
    serializer = get_serializer()
    return serializer.dumps(data, salt=salt)

def verify_token(token, salt: str, max_age_sec=3600):
    """Verifies a token's signature and expiration."""
    serializer = get_serializer()
    try:
        data = serializer.loads(token, salt=salt, max_age=max_age_sec)
        return data
    except (SignatureExpired, BadSignature):
        logger.warning("Invalid or expired token received.")
        return None

# ===========================
# Core Authentication Logic
# ===========================

def request_password_reset(email: str):
    """Generates a password reset token and sends it via email."""
    with get_session_scope() as session:
        user = session.query(UserAccount).filter_by(email=email).first()
        if user:
            token = generate_token({"user_id": str(user.id)}, salt='password-reset', expires_in_sec=3600)
            reset_url = f"https://brightacts.com/reset-password?token={token}" # Use your actual front-end URL
            subject = "Password Reset Request"
            body = f"Click the link to reset your password: {reset_url}"
            send_email(user.email, subject, body)
            logger.info(f"Sent password reset email to {email}")
    # We don't return failure to prevent email enumeration attacks

def confirm_password_reset(token: str, new_password: str) -> bool:
    """Verifies a reset token and updates the user's password."""
    payload = verify_token(token, salt='password-reset', max_age_sec=3600)
    if not payload or "user_id" not in payload:
        return False
    
    with get_session_scope() as session:
        user = session.query(UserAccount).filter_by(id=payload["user_id"]).first()
        if not user:
            return False
        user.password_hash = generate_password_hash(new_password)
        session.commit()
        logger.info(f"Password updated successfully for user_id: {user.id}")
        return True

# --- Function for status page ---
def get_auth_status():
    """Returns the current operational status of the authentication system."""
    return {"active": True, "healthy": True, "info": "Authentication system operational"}
