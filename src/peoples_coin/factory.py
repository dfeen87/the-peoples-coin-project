from flask import Blueprint, jsonify, request, make_response # Ensure make_response is imported
import logging # Import logging if not already present

# Initialize the Blueprint for your API routes
api_bp = Blueprint('api', __name__)

logger = logging.getLogger(__name__)

# Example of a root API route (optional, but common)
@api_bp.route('/', methods=['GET'])
def api_root():
    return jsonify({"message": "Welcome to the Peoples Coin API!"}), 200

# Your existing check_username_availability route, now with direct CORS headers for testing
@api_bp.route('/v1/users/username-check/<username>', methods=['GET'])
def check_username_availability(username):
    logger.info(f"Received request for username check: {username}")
    # In a real application, you would query your database here
    # For this test, let's simulate a username being taken
    is_available = (username.lower() != "brightacts") # Example: 'brightacts' is taken

    response = make_response(jsonify({"available": is_available}), 200)

    # --- TEMPORARY CORS HEADERS FOR DIAGNOSIS ---
    # These headers are added directly to this specific response.
    # If this works, it means Flask-CORS's global configuration is not being applied correctly.
    # If this DOES NOT work, the issue is likely upstream (e.g., Google Cloud Run's proxy).
    response.headers['Access-Control-Allow-Origin'] = 'https://brightacts.com'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS' # Include OPTIONS for preflight requests
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Credentials'] = 'true' # If your frontend sends cookies/auth headers

    logger.info(f"Sending response for username check with CORS headers for origin: https://brightacts.com")
    return response

# Example of another route (keep your existing routes as they are)
# @api_bp.route('/v1/users/register-wallet', methods=['POST'])
# def register_user_wallet():
#     # Your existing logic for registering a user wallet
#     data = request.get_json()
#     username = data.get('username')
#     public_key = data.get('public_key')
#     encrypted_private_key = data.get('encrypted_private_key')
#     recaptcha_token = data.get('recaptcha_token')
#
#     # ... process data, save to DB ...
#
#     return jsonify({"message": "User wallet registered successfully"}), 201

# ... (add any other routes that are part of your api_bp blueprint) ...

