import os
import requests
import logging # Import logging
from flask import Flask, request, jsonify

# Assuming 'app' is your Flask application instance, defined in factory.py
# If this file is part of a blueprint, 'app' might be handled differently,
# but for now, we'll assume it's directly accessible or passed.
# Make sure your app is correctly initialized with CORS as discussed before.

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Assuming 'app' is already initialized, e.g., if this is part of routes/auth.py blueprint ---
# If this is a standalone file, you might need to import app from factory or similar.
# For simplicity, I'm showing the route function and its dependencies.
# You will integrate this into your existing Flask route structure.

# IMPORTANT: Ensure RECAPTCHA_SECRET_KEY is set in your backend's environment variables
# This should be the Secret Key corresponding to your chosen v3 Public Site Key (6LeE0pQrAAAAAML8x8JqtfryKhZ9bpvLRacQzH1F)

@app.route("/api/verify_login", methods=["POST"])
def verify_login():
    data = request.get_json()

    # Get reCAPTCHA token from the frontend request body
    recaptcha_token = data.get("token")
    if not recaptcha_token:
        return jsonify({"error": "Missing reCAPTCHA token"}), 400

    # Get the reCAPTCHA v3 Secret Key from environment variables
    RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY")
    if not RECAPTCHA_SECRET_KEY:
        logger.error("RECAPTCHA_SECRET_KEY environment variable is not set in backend!")
        return jsonify({"error": "Server configuration error"}), 500

    # Google's reCAPTCHA verification endpoint
    verify_url = "https://www.google.com/recaptcha/api/siteverify"
    verify_payload = {
        "secret": RECAPTCHA_SECRET_KEY,
        "response": recaptcha_token,
        # "remoteip": request.remote_addr # Optional: include user's IP for better bot detection
    }

    try:
        response = requests.post(verify_url, data=verify_payload, timeout=5) # Added timeout
        response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
        recaptcha_result = response.json()

        if not recaptcha_result.get("success"):
            logger.warning(f"reCAPTCHA v3 verification failed: {recaptcha_result.get('error-codes')}")
            return jsonify({"error": "reCAPTCHA verification failed. Please try again."}), 403 # Changed to 403 Forbidden
        
        # --- Crucial for reCAPTCHA v3: Check score and action ---
        score = recaptcha_result.get("score")
        action = recaptcha_result.get("action")
        
        if score is None or score < 0.5: # Adjust threshold as needed (0.5 is a common starting point)
            logger.warning(f"reCAPTCHA v3 score too low ({score}) for action '{action}'")
            return jsonify({"error": "reCAPTCHA score too low. Please try again."}), 403
        
        if action != 'login': # Ensure this matches the action you send from frontend for login
            logger.warning(f"reCAPTCHA v3 action mismatch: expected 'login', got '{action}'")
            return jsonify({"error": "reCAPTCHA action mismatch."}), 403

        # If reCAPTCHA v3 check passes
        logger.info(f"reCAPTCHA v3 check passed for action '{action}' with score {score}. User is verified.")
        
        # --- ADD YOUR ACTUAL LOGIN LOGIC HERE ---
        # This is where you would typically:
        # 1. Verify user credentials (email/password) against your database or Firebase Auth.
        # 2. Authenticate the user.
        # 3. Issue a session token or similar.

        return jsonify({"message": "Login verification successful"}), 200

    except requests.exceptions.RequestException as e:
        logger.error(f"Error during reCAPTCHA siteverify request: {e}")
        return jsonify({"error": "Failed to verify reCAPTCHA with Google."}), 500
    except ValueError as e: # Catch JSON decoding errors more specifically
        logger.error(f"Failed to decode reCAPTCHA siteverify response as JSON: {e}")
        return jsonify({"error": "Failed to process reCAPTCHA response."}), 500

# --- The if __name__ == "__main__": block should ideally be in your main app.py or wsgi.py ---
# if __name__ == "__main__":
#     app.run(debug=True)
