from flask import Flask, request, jsonify
from recaptcha_verification import verify_recaptcha_v2

app = Flask(__name__)

@app.route("/api/verify_login", methods=["POST"])
def verify_login():
    data = request.get_json()

    # Get reCAPTCHA token from the frontend request body
    token = data.get("token")
    if not token:
        return jsonify({"error": "Missing reCAPTCHA token"}), 400

    # Verify the token using the function you imported
    try:
        # This is the corrected line
        verification_success = verify_recaptcha_v2(token)
    except Exception as e:
        return jsonify({"error": f"Verification error: {str(e)}"}), 500

    if not verification_success:
        return jsonify({"error": "reCAPTCHA verification failed"}), 403

    # If the check passes, you would add your actual login logic here
    print("reCAPTCHA check passed, user is verified.")
    
    # Verification passed
    return jsonify({"message": "Verification successful"}), 200

if __name__ == "__main__":
    app.run(debug=True)
