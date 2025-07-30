from flask import Flask, request, jsonify
from recaptcha_verification import verify_recaptcha_enterprise

app = Flask(__name__)

@app.route("/api/verify_login", methods=["POST"])
def verify_login():
    data = request.get_json()

    # Get reCAPTCHA token from the frontend request body
    token = data.get("token")
    if not token:
        return jsonify({"error": "Missing reCAPTCHA token"}), 400

    # Verify the token using your backend function
    try:
        verification_success = verify_recaptcha_enterprise(token)
    except Exception as e:
        return jsonify({"error": f"Verification error: {str(e)}"}), 500

    if not verification_success:
        return jsonify({"error": "reCAPTCHA verification failed"}), 403

    # Verification passed
    return jsonify({"success": True}), 200

if __name__ == "__main__":
    app.run(debug=True)

