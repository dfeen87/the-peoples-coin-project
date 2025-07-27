import http
import logging
from functools import wraps

from flask import Blueprint, request, jsonify, g
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError

from peoples_coin.extensions import db
from peoples_coin.utils.auth import require_firebase_token
from peoples_coin.models import UserAccount # Ensure this import is present

logger = logging.getLogger(__name__)

# --- THIS IS THE CORRECTED LINE ---
# The blueprint is renamed to be unique and the url_prefix is removed.
# Your routes/__init__.py file will handle the prefix.
user_api_bp = Blueprint("user_api", __name__)


# --- User-related Routes ---

@user_api_bp.route("/users/username-check/<username>", methods=["GET"])
def check_username_availability(username):
    """Checks if a username is available in the database."""
    logger.info(f"Checking database for username availability for: {username}")
    try:
        user_exists = db.session.query(UserAccount).filter(UserAccount.username.ilike(username)).first()
        is_available = (user_exists is None)
        logger.info(f"Username '{username}' is available: {is_available}")
        return jsonify({"available": is_available}), http.HTTPStatus.OK
    except Exception as e:
        logger.error(f"Database error while checking username '{username}': {e}", exc_info=True)
        return jsonify({"available": False, "error": "Database query failed"}), http.HTTPStatus.INTERNAL_SERVER_ERROR


@user_api_bp.route("/users/register-wallet", methods=["POST"])
@require_firebase_token
def register_user_wallet():
    """Creates a new user record in the database."""
    firebase_user = g.firebase_user
    logger.info(f"Attempting to register new user wallet for Firebase UID: {firebase_user['uid']}")
    try:
        data = request.get_json()
        if not data:
            return jsonify(error="Missing JSON body"), http.HTTPStatus.BAD_REQUEST

        new_user = UserAccount(
            id=firebase_user['uid'],
            email=firebase_user['email'],
            username=data.get('username'),
            public_key=data.get('public_key'),
            encrypted_private_key=data.get('encrypted_private_key')
        )
        db.session.add(new_user)
        db.session.commit()
        logger.info(f"Successfully created user record for {new_user.username}")
        return jsonify(new_user.to_dict()), http.HTTPStatus.CREATED
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="User with this ID or username already exists."), http.HTTPStatus.CONFLICT
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to register user wallet for UID {firebase_user['uid']}: {e}", exc_info=True)
        return jsonify(error="An internal error occurred."), http.HTTPStatus.INTERNAL_SERVER_ERROR


@user_api_bp.route("/profile", methods=["GET"])
@require_firebase_token
def get_user_profile():
    """Returns the authenticated user's profile information."""
    user = g.user
    if not user:
        return jsonify(error="User not authenticated or found in local database"), http.HTTPStatus.UNAUTHORIZED
    return jsonify(user.to_dict()), http.HTTPStatus.OK

# Note: The health and readiness checks were removed as they are not user-specific
# and are better placed in a separate, top-level routes file if needed.

