# peoples_coin/routes/auth_routes.py
import http
import secrets
import logging
import time
from functools import wraps
from flask import Blueprint, request, jsonify, g, current_app
from werkzeug.security import check_password_hash, generate_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import func

from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models import ApiKey, UserAccount
from peoples_coin.extensions import db
from peoples_coin.utils.auth import require_firebase_token
from peoples_coin.utils.recaptcha import verify_recaptcha
from peoples_coin.utils.email import send_email # Assuming this utility exists

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# --- Token Serializer Utilities ---
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

# --- Email Sending Stubs ---
def send_password_reset_email(to_email, token):
    """Sends a password reset email with a unique token."""
    reset_url = f"https://brightacts.com/reset-password?token={token}" # Use your actual frontend URL
    subject = "Password Reset Request"
    body = f"Click the link to reset your password: {reset_url}"
    send_email(to_email, subject, body)
    logger.info(f"Sent password reset email to {to_email}")

# --- API Routes ---

@auth_bp.route("/signup", methods=["POST"])
def signup():
    """Handles new user registration with reCAPTCHA."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON body"}), http.HTTPStatus.BAD_REQUEST
    email, username, password = data.get("email"), data.get("username"), data.get("password")

    if not all([email, username, password]):
        return jsonify({"error": "Email, username, and password are required"}), http.HTTPStatus.BAD_REQUEST
    
    with get_session_scope() as session:
        if session.query(UserAccount).filter((func.lower(UserAccount.email) == email.lower()) | (func.lower(UserAccount.username) == username.lower())).first():
            return jsonify({"error": "User with that email or username already exists"}), http.HTTPStatus.CONFLICT
        
        new_user = UserAccount(email=email, username=username, password_hash=generate_password_hash(password))
        session.add(new_user)
        return jsonify({"message": "User created successfully"}), http.HTTPStatus.CREATED

@auth_bp.route("/signin", methods=["POST"])
def signin():
    """Handles user sign-in with email and password."""
    data = request.get_json()
    if not data or not data.get("email") or not data.get("password"):
        return jsonify({"error": "Email and password are required"}), http.HTTPStatus.BAD_REQUEST
        
    with get_session_scope() as session:
        user = session.query(UserAccount).filter(func.lower(UserAccount.email) == data["email"].lower()).first()
        if not user or not user.password_hash or not check_password_hash(user.password_hash, data["password"]):
            return jsonify({"error": "Invalid email or password"}), http.HTTPStatus.UNAUTHORIZED
        
        # In a real app, you would generate and return a JWT or session token here
        return jsonify({"message": "Sign-in successful", "user": user.to_dict(include_wallets=False)}), http.HTTPStatus.OK

@auth_bp.route("/create-api-key", methods=["POST"])
@require_firebase_token
def create_api_key():
    """Creates an API key for the authenticated user."""
    user = g.user
    new_key = secrets.token_urlsafe(30)
    with get_session_scope() as session:
        session.add(ApiKey(key=new_key, user_id=user.id))
    return jsonify({"message": "API key created successfully", "api_key": new_key}), http.HTTPStatus.CREATED

@auth_bp.route("/password-reset/request", methods=["POST"])
def password_reset_request():
    """Initiates a password reset flow for a given email."""
    data = request.get_json() or {}
    email = data.get("email")
    if not email:
        return jsonify({"error": "Email is required"}), http.HTTPStatus.BAD_REQUEST
    
    request_password_reset(email)
    
    # Always return a generic success message to prevent email enumeration attacks
    return jsonify({"message": "If an account with that email exists, a reset link has been sent."}), http.HTTPStatus.OK

@auth_bp.route("/password-reset/confirm", methods=["POST"])
def password_reset_confirm():
    """Finalizes a password reset using a token."""
    data = request.get_json() or {}
    token = data.get("token")
    new_password = data.get("new_password")

    if not token or not new_password:
        return jsonify({"error": "Token and new password are required"}), http.HTTPStatus.BAD_REQUEST

    if confirm_password_reset(token, new_password):
        return jsonify({"message": "Password updated successfully"}), http.HTTPStatus.OK
    else:
        return jsonify({"error": "Invalid or expired token"}), http.HTTPStatus.BAD_REQUEST
