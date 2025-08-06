import http
import secrets
from flask import Blueprint, request, jsonify, g
from werkzeug.security import check_password_hash, generate_password_hash
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import ApiKey, UserAccount
from peoples_coin.extensions import db
from peoples_coin.utils.auth import require_firebase_token
from peoples_coin.utils.recaptcha_enterprise import verify_recaptcha  # Added import

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")
KEY_ERROR = "error"
KEY_MESSAGE = "message"

# ---------------------------
# Create API Key
# ---------------------------
@auth_bp.route("/create-api-key", methods=["POST"])
def create_api_key():
    if not request.is_json:
        return jsonify({KEY_ERROR: "Content-Type must be application/json"}), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    data = request.get_json()
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({KEY_ERROR: "Missing 'user_id' in request body"}), http.HTTPStatus.BAD_REQUEST

    with get_session_scope() as session:
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

# ---------------------------
# Sign-in using email/password
# ---------------------------
@auth_bp.route("/signin", methods=["POST"])
def signin():
    if not request.is_json:
        return jsonify({KEY_ERROR: "Content-Type must be application/json"}), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({KEY_ERROR: "Email and password are required"}), http.HTTPStatus.BAD_REQUEST

    with get_session_scope() as session:
        user = session.query(UserAccount).filter_by(email=email).first()
        if not user:
            return jsonify({KEY_ERROR: "Invalid email or password"}), http.HTTPStatus.UNAUTHORIZED

        if not user.password_hash or not check_password_hash(user.password_hash, password):
            return jsonify({KEY_ERROR: "Invalid email or password"}), http.HTTPStatus.UNAUTHORIZED

        # Return user info
        return jsonify({
            KEY_MESSAGE: "Sign-in successful",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "balance": str(user.balance),
                "goodwill_coins": user.goodwill_coins,
            }
        }), http.HTTPStatus.OK

# ---------------------------
# Get Current Authenticated User (Auto-create if missing)
# ---------------------------
@auth_bp.route("/users/me", methods=["GET"])
@require_firebase_token
def get_current_user():
    """Returns the authenticated user's profile from DB. Creates DB record if missing."""
    with get_session_scope() as session:
        # Try to find user in DB by Firebase UID
        user = session.query(UserAccount).filter_by(firebase_uid=g.user.firebase_uid).first()

        # Auto-create DB record if not found
        if not user:
            user = UserAccount(
                firebase_uid=g.user.firebase_uid,
                email=g.user.email,
                username=g.user.username or g.user.email.split("@")[0],
                password_hash=generate_password_hash(secrets.token_hex(8)),  # Random internal password
                balance=0,
                goodwill_coins=0
            )
            session.add(user)
            session.flush()

        # Return full user profile
        return jsonify({
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "balance": str(user.balance),
            "goodwill_coins": user.goodwill_coins
        }), http.HTTPStatus.OK

# ---------------------------
# Sign-up new user (with reCAPTCHA verification)
# ---------------------------
@auth_bp.route("/signup", methods=["POST"])
def signup():
    if not request.is_json:
        return jsonify({KEY_ERROR: "Content-Type must be application/json"}), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    data = request.get_json()
    email = data.get("email")
    username = data.get("username")
    password = data.get("password")
    recaptcha_token = data.get("recaptchaToken")  # Get reCAPTCHA token from frontend

    if not email or not username or not password or not recaptcha_token:
        return jsonify({KEY_ERROR: "Email, username, password, and recaptchaToken are required"}), http.HTTPStatus.BAD_REQUEST

    # Verify reCAPTCHA
    RECAPTCHA_EXPECTED_ACTION = "signup"
    user_ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")

    if not verify_recaptcha(recaptcha_token, RECAPTCHA_EXPECTED_ACTION, user_ip, user_agent):
        return jsonify({KEY_ERROR: "Invalid or failed reCAPTCHA verification"}), http.HTTPStatus.BAD_REQUEST

    with get_session_scope() as session:
        # Check if email or username already exists
        existing_user = session.query(UserAccount).filter(
            (UserAccount.email == email) | (UserAccount.username == username)
        ).first()

        if existing_user:
            return jsonify({KEY_ERROR: "User with that email or username already exists"}), http.HTTPStatus.CONFLICT

        # Create new user with hashed password
        user = UserAccount(
            email=email,
            username=username,
            password_hash=generate_password_hash(password),
            balance=0,
            goodwill_coins=0
        )
        session.add(user)
        session.flush()

        return jsonify({
            KEY_MESSAGE: "User created successfully",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "balance": str(user.balance),
                "goodwill_coins": user.goodwill_coins
            }
        }), http.HTTPStatus.CREATED

