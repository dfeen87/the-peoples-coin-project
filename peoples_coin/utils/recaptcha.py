import os
import requests
import json
import logging

logger = logging.getLogger(__name__)

# Read reCAPTCHA keys from environment variables
RECAPTCHA_PROJECT_ID = os.environ.get("RECAPTCHA_PROJECT_ID")
RECAPTCHA_SITE_KEY_PROD = os.environ.get("RECAPTCHA_SITE_KEY")
RECAPTCHA_API_KEY = os.environ.get("RECAPTCHA_API_KEY")

def verify_recaptcha(token: str, expected_action: str, user_ip: str = None, user_agent: str = None):
    # Check if a critical key is missing and log an error
    if not RECAPTCHA_PROJECT_ID or not RECAPTCHA_SITE_KEY_PROD or not RECAPTCHA_API_KEY:
        logger.error("🚨 reCAPTCHA environment variables are not set correctly.")
        return False, "Server-side reCAPTCHA configuration error."

    url = f"https://recaptchaenterprise.googleapis.com/v1/projects/{RECAPTCHA_PROJECT_ID}/assessments?key={RECAPTCHA_API_KEY}"

    payload = {
        "event": {
            "token": token,
            "siteKey": RECAPTCHA_SITE_KEY_PROD,
            "expectedAction": expected_action,
        }
    }

    if user_ip:
        payload["event"]["userIpAddress"] = user_ip
    if user_agent:
        payload["event"]["userAgent"] = user_agent

    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()

        data = response.json()
        if data.get("tokenProperties", {}).get("valid", False) and \
           data.get("riskAnalysis", {}).get("score", 0) >= 0.5:
            return True, "reCAPTCHA verification successful."
        else:
            return False, data.get("tokenProperties", {}).get("invalidReason", "Unknown reason")

    except requests.RequestException as e:
        logger.error(f"Error verifying recaptcha: {e}", exc_info=True)
        return False, f"Error verifying recaptcha: {e}"


