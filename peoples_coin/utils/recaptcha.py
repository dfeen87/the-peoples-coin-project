import requests

RECAPTCHA_PROJECT_ID = "brightacts-frontend-50f58"  # Your Google Cloud project ID
RECAPTCHA_SITE_KEY_PROD = "6LeE0pQrAAAAAML8x8JqtfryKhZ9bpvLRacQzH1F"  # Your frontend site key (matches what client uses)
RECAPTCHA_API_KEY = "AIzaSyC0PZq7NkMouTR4-DDiCGiMLdfLB7AREgc"  # Your backend API key for verification

def verify_recaptcha(token: str, expected_action: str, user_ip: str = None, user_agent: str = None) -> bool:
    url = f"https://recaptchaenterprise.googleapis.com/v1/projects/{RECAPTCHA_PROJECT_ID}/assessments?key={RECAPTCHA_API_KEY}"

    payload = {
        "event": {
            "token": token,
            "siteKey": RECAPTCHA_SITE_KEY,
        }
    }
    if user_ip:
        payload["event"]["userIpAddress"] = user_ip
    if user_agent:
        payload["event"]["userAgent"] = user_agent

    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error verifying recaptcha: {e}")
        return False

    data = response.json()

    if not data.get("tokenProperties", {}).get("valid", False):
        print(f"Invalid recaptcha token: {data.get('tokenProperties', {}).get('invalidReason')}")
        return False

    if data.get("tokenProperties", {}).get("action") != expected_action:
        print(f"Unexpected recaptcha action: {data.get('tokenProperties', {}).get('action')} (expected {expected_action})")
        return False

    score = data.get("riskAnalysis", {}).get("score", 0)
    if score < 0.5:
        print(f"Low recaptcha score: {score}")
        return False

    return True

