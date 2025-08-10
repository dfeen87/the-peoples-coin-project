import os
from google.cloud import recaptchaenterprise_v1
from google.oauth2 import service_account

# Load values from environment variables
KEY_PATH = os.environ.get(
    "FIREBASE_CREDENTIAL_PATH",
    "/app/peoples_coin/heroic-tide-428421-q7-9ff07058342c.json"
)
PROJECT_ID = os.environ.get("RECAPTCHA_PROJECT_ID", "")
SITE_KEY = os.environ.get("RECAPTCHA_SITE_KEY", "")

if not PROJECT_ID or not SITE_KEY:
    raise ValueError("Missing RECAPTCHA_PROJECT_ID or RECAPTCHA_SITE_KEY in environment variables")

# Load credentials
credentials = service_account.Credentials.from_service_account_file(KEY_PATH)
client = recaptchaenterprise_v1.RecaptchaEnterpriseServiceClient(credentials=credentials)

def verify_recaptcha(token: str, expected_action: str) -> bool:
    assessment = recaptchaenterprise_v1.Assessment()
    assessment.event.token = token
    assessment.event.site_key = SITE_KEY

    parent = f"projects/{PROJECT_ID}"
    response = client.create_assessment(parent=parent, assessment=assessment)

    if not response.token_properties.valid:
        print(f"Invalid token: {response.token_properties.invalid_reason}")
        return False

    if response.token_properties.action != expected_action:
        print(f"Unexpected action: {response.token_properties.action}")
        return False

    score = response.risk_analysis.score
    if score < 0.5:
        print(f"Low score: {score}")
        return False

    return True

