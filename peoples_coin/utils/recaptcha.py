# peoples_coin/utils/recaptcha.py
from google.cloud import recaptchaenterprise_v1

def verify_recaptcha(token, action, user_ip, user_agent):
    project_id = "heroic-tide-428421-q7" 
    site_key = "6LeE0pQrAAAAAML8x8JqtfryKhZ9bpvLRacQzH1F"

    client = recaptchaenterprise_v1.RecaptchaEnterpriseServiceClient()

    event = recaptchaenterprise_v1.Event(
        site_key=site_key,
        token=token,
        user_ip_address=user_ip,
        user_agent=user_agent,
    )

    assessment = recaptchaenterprise_v1.Assessment(event=event)
    parent = f"projects/{project_id}"

    request = recaptchaenterprise_v1.CreateAssessmentRequest(
        assessment=assessment,
        parent=parent,
    )

    response = client.create_assessment(request)

    if not response.token_properties.valid:
        return False, f"Invalid token: {response.token_properties.invalid_reason}"

    if response.token_properties.action != action:
        return False, "Action mismatch"

    score = response.risk_analysis.score
    if score < 0.5:
        return False, f"Low score ({score}) - possible bot"

    return True, f"Passed with score {score}"

