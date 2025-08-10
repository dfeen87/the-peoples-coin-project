import http
import logging
import time
from functools import wraps
from flask import Blueprint, request, jsonify, g, current_app
from werkzeug.security import generate_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from peoples_coin.extensions import db
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import UserAccount
from peoples_coin.utils.auth import require_firebase_token
from peoples_coin.utils.email import send_email  # You will implement this for real email sending

logger = logging.getLogger(__name__)
auth_bp = Blueprint("authentication", __name__, url_prefix="/api/auth")

# ===========================
# Simple in-memory rate limiter (per IP)
# ===========================
RATE_LIMIT_STORE = {}

def rate_limit(max_calls, period_sec):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            ip = request.remote_addr or "unknown"
            now = time.time()
            calls = RATE_LIMIT_STORE.get(ip, [])
            # Filter calls within period
            calls = [t for t in calls if t > now - period_sec]
            if len(calls) >= max_calls:
                logger.warning(f"Rate limit exceeded for IP {ip}")
                return jsonify({"error": "Too many requests, slow down."}), http.HTTPStatus.TOO_MANY_REQUESTS
            calls.append(now)
            RATE_LIMIT_STORE[ip] = calls
            return f(*args, **kwargs)
        return wrapped
    return decorator

# ===========================
# Token Serializer Utilities
# ===========================
def get_serializer(secret_key=None):
    secret_key = secret_key or current_app.config.get("SECRET_KEY")
    return URLSafeTimedSerializer(secret_key)

def generate_token(data: dict, expires_in=3600):
    serializer = get_serializer()
    token = serializer.dumps(data)
    return token

def verify_token(token, max_age=3600):
    serializer = get_serializer()
    try:
        data = serializer.loads(token, max_age=max_age)
        return data
    except SignatureExpired:
        logger.info("Token expired")
        return None
    except BadSignature:
        logger.info("Bad token signature")
        return None

# ===========================
# EMAIL SENDING (Stub)
# ===========================
def send_password_reset_email(to_email, token):
    reset_url = f"https://yourfrontend.com/reset-password?token={token}"
    subject = "Password Reset Request"
    body = f"Click the link to reset your password: {reset_url}"
    send_email(to_email, subject, body)
    logger.info(f"Sent password reset email to {to_email}")

def send_verification_email(to_email, token):
    verify_url = f"https://yourfrontend.com/verify-email?token={token}"
    subject = "Verify Your Email Address"
    body = f"Click the link to verify your email: {verify_url}"
    send_email(to_email, subject, body)
    logger.info(f"Sent email verification to {to_email}")

# ===========================
# Routes
# ===========================

# Password reset request (rate limited)
@auth_bp.route("/password-reset/request", methods=["POST"])
@rate_limit(max_calls=5, period_sec=60*15)  # 5 requests per 15 minutes per IP
def password_reset_request():
    data = request.get_json() or {}
    email = data.get("email")
    if not email:
        return jsonify({"error": "Email is required"}), http.HTTPStatus.BAD_REQUEST

    with get_session_scope() as session:
        user = session.query(UserAccount).filter_by(email=email).first()
        if user:
            token = generate_token({"user_id": str(user.id)}, expires_in=3600)
            send_password_reset_email(email, token)

    # Always return success message to avoid email enumeration
    return jsonify({"message": "If an account with that email exists, a reset link has been sent."}), http.HTTPStatus.OK

# Password reset confirm
@auth_bp.route("/password-reset/confirm", methods=["POST"])
def password_reset_confirm():
    data = request.get_json() or {}
    token = data.get("token")
    new_password = data.get("new_password")

    if not token or not new_password:
        return jsonify({"error": "Token and new password are required"}), http.HTTPStatus.BAD_REQUEST

    payload = verify_token(token)
    if not payload or "user_id" not in payload:
        return jsonify({"error": "Invalid or expired token"}), http.HTTPStatus.BAD_REQUEST

    user_id = payload["user_id"]
    with get_session_scope() as session:
        user = session.query(UserAccount).filter_by(id=user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), http.HTTPStatus.NOT_FOUND

        user.password_hash = generate_password_hash(new_password)
        session.commit()

    return jsonify({"message": "Password updated successfully"}), http.HTTPStatus.OK

# Email verification request (authenticated)
@auth_bp.route("/email-verification/request", methods=["POST"])
@require_firebase_token
def email_verification_request():
    user = g.user
    if not user:
        return jsonify({"error": "User not authenticated"}), http.HTTPStatus.UNAUTHORIZED

    token = generate_token({"user_id": str(user.id)}, expires_in=3600*24)
    send_verification_email(user.email, token)

    return jsonify({"message": "Verification email sent"}), http.HTTPStatus.OK

# Email verification confirm
@auth_bp.route("/email-verification/confirm", methods=["POST"])
def email_verification_confirm():
    data = request.get_json() or {}
    token = data.get("token")

    if not token:
        return jsonify({"error": "Verification token is required"}), http.HTTPStatus.BAD_REQUEST

    payload = verify_token(token, max_age=3600*24)
    if not payload or "user_id" not in payload:
        return jsonify({"error": "Invalid or expired token"}), http.HTTPStatus.BAD_REQUEST

    user_id = payload["user_id"]
    with get_session_scope() as session:
        user = session.query(UserAccount).filter_by(id=user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), http.HTTPStatus.NOT_FOUND

        user.email_verified = True
        session.commit()

    return jsonify({"message": "Email verified successfully"}), http.HTTPStatus.OK

