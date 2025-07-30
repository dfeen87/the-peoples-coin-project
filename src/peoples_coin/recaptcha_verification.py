import json
import requests
import logging
from google.oauth2 import service_account
from google.auth.transport.requests import Request

SERVICE_ACCOUNT_FILE = 'recaptcha-service.json'
PROJECT_ID = 'heroic-tide-428421'
SITE_KEY = '6LcwyYUrAAAAAE2Bv6bXHjq23zTBE49ABYmi4ccs'

def verify_recaptcha_enterprise(token: str, expected_action: str = 'login') -> bool:
    """
    Verifies the reCAPTCHA Enterprise token using Google's API.

    Args:
        token (str): The reCAPTCHA token received from the client.
        expected_action (str): Action expected (e.g., 'login').

    Returns:
        bool: True if verified and score meets threshold; False otherwise.
    """
    if not token:
        logging.warning("No reCAPTCHA token provided.")
        return False

    try:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        credentials.refresh(Request())
        access_token = credentials.token

        url = f"https://recaptchaenterprise.googleapis.com/v1/projects/{PROJECT_ID}/assessments"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        body = {
            "event": {
                "token": token,
                "siteKey": SITE_KEY,
                "expectedAction": expected_action
                # "projectNumber": "YOUR_PROJECT_NUMBER"  # Optional, more accurate
            }
        }

        response = requests.post(url, headers=headers, data=json.dumps(body))

        if response.status_code != 200:
            logging.error(f"reCAPTCHA API error {response.status_code}: {response.text}")
            return False

        result = response.json()
        score = result.get("riskAnalysis", {}).get("score", 0.0)
        logging.info(f"reCAPTCHA score: {score:.2f} (action: {expected_action})")

        return score >= 0.5

    except Exception as e:
        logging.exception("reCAPTCHA verification failed.")
        return False

