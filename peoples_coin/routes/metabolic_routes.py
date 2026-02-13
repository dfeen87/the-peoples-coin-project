# src/peoples_coin/routes/metabolic_routes.py

import logging
import http
import uuid

from flask import Blueprint, request, jsonify, make_response, Response, g
from pydantic import ValidationError

# Assuming these are defined in your project structure
from peoples_coin.services.goodwill_service import goodwill_service, GoodwillSubmissionError
from peoples_coin.utils.auth import require_firebase_token  # Example security
from peoples_coin.validate.schemas import GoodwillActionSchema
from peoples_coin.validate.exceptions import UserNotFoundError

logger = logging.getLogger(__name__)

metabolic_bp = Blueprint('metabolic', __name__, url_prefix='/metabolic')


# --- Request Tracing & Logging ---

@metabolic_bp.before_request
def extract_correlation_id() -> None:
    """Ensures a correlation ID is present for every request for tracing."""
    g.correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))


def log_with_correlation(level: str, message: str, **kwargs) -> None:
    """Helper to include the correlation ID in log messages."""
    prefix = f"[CorrelationID: {g.correlation_id}] "
    getattr(logger, level)(prefix + message, **kwargs)


# --- Goodwill Scoring Logic ---

# Expanded base scores for known goodwill actions (out of 100)
base_scores = {
    "donate blood": 35,
    "donate platelets": 40,
    "volunteer": 25,
    "helped stranger": 20,
    "community cleanup": 30,
    "food drive donation": 30,
    "mentoring youth": 35,
    "fundraising event": 25,
    "tutor student": 20,
    "rescue animal": 40,
    "organize charity": 35,
    "support elderly": 25,
    "blood drive": 35,
    "plant trees": 30,
    "donate clothes": 20,
    "foster pet": 30,
    "emergency aid": 45,
    "care for sick": 30,
    "random act of kindness": 15,
    "share skills": 20,
    "donate money": 35,
    "advocate cause": 25,
    "donate food": 25,
    "participate march": 20,
    "help neighbor": 20,
    "provide shelter": 40,
    "support mental health": 30,
}

def calculate_goodwill_score(title: str, description: str, time_spent_minutes: int, user_impact_score: int) -> int:
    """
    Calculate goodwill score out of 100 based on title base score,
    description length, time spent, and user self-rated impact score.
    """
    title_key = title.strip().lower()
    base_score = base_scores.get(title_key, 10)  # Default base if not found

    # Description score: capped, 0.1 points per char up to 20 points max
    description_score = min(len(description) * 0.1, 20)

    # Time spent score: max 25 points, capped at 180 minutes (3 hours)
    time_score = min(time_spent_minutes / 180 * 25, 25)

    # User impact score: user rates 1-100, normalized to 20 points max
    impact_score = min(user_impact_score / 100 * 20, 20)

    total_score = base_score + description_score + time_score + impact_score

    # Cap the total score at 100 max
    final_score = min(int(total_score), 100)
    return final_score


# --- API Routes ---

@metabolic_bp.route('/status', methods=['GET'])
def metabolic_status() -> Response:
    """Health check endpoint for the Metabolic System."""
    log_with_correlation("debug", "Metabolic system status check called.")
    return make_response(jsonify(status="success", message="Metabolic System operational"), http.HTTPStatus.OK)


@metabolic_bp.route('/submit_goodwill', methods=['POST'])
@require_firebase_token  # Secure this public-facing endpoint
def submit_goodwill() -> Response:
    """
    Receives a goodwill action, validates it, calculates score,
    and delegates to the service layer for asynchronous processing.
    """
    log_with_correlation("info", "Received goodwill submission request.")

    if not request.is_json:
        log_with_correlation("warning", "Request missing JSON body or has incorrect Content-Type.")
        return make_response(jsonify(status="error", error="Content-Type must be application/json"), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE)

    try:
        # 1. Validate the incoming data structure
        action_data = GoodwillActionSchema(**request.get_json())

        # 2. Look up the database user from firebase_uid to get the actual user ID
        from peoples_coin.models.db_utils import get_session_scope
        from peoples_coin.models import UserAccount
        with get_session_scope() as session:
            db_user = session.query(UserAccount).filter_by(firebase_uid=g.user.firebase_uid).first()
            if not db_user:
                log_with_correlation("error", "User account not found in database")
                return make_response(jsonify(status="error", error="User account not found"), http.HTTPStatus.NOT_FOUND)
            action_data.performer_user_id = db_user.id

        # 3. Calculate goodwill score with new scoring logic
        score = calculate_goodwill_score(
            title=action_data.title,
            description=action_data.description or "",
            time_spent_minutes=action_data.time_spent_minutes or 0,
            user_impact_score=action_data.user_impact_score or 50,  # Default mid impact if none given
        )

        # Attach the score to the action data for persistence
        action_data.calculated_score = score

        log_with_correlation("info", f"Calculated goodwill score: {score}")

        # 4. Delegate to the service layer for processing
        result = goodwill_service.submit_and_queue_goodwill_action(action_data)

        log_with_correlation("info", f"GoodwillAction ID {result['action_id']} accepted and queued.")

        # 5. Return a success response
        return make_response(jsonify(
            status="success",
            message="Goodwill action accepted and queued for processing.",
            action_id=result.get("action_id"),
            calculated_score=score,
            status_code=http.HTTPStatus.ACCEPTED.value  # Use value for consistency
        ), http.HTTPStatus.ACCEPTED)

    except ValidationError as ve:
        log_with_correlation("warning", f"Pydantic validation failed: {ve.errors()}")
        return make_response(jsonify(status="error", error="Invalid data format provided", details=ve.errors()), http.HTTPStatus.BAD_REQUEST)

    except UserNotFoundError as unfe:
        log_with_correlation("warning", f"User not found during goodwill submission: {unfe}")
        return make_response(jsonify(status="error", error="User specified in action not found."), http.HTTPStatus.NOT_FOUND)

    except GoodwillSubmissionError as gse:
        log_with_correlation("error", f"A known submission error occurred: {gse}")
        return make_response(jsonify(status="error", error=str(gse)), http.HTTPStatus.UNPROCESSABLE_ENTITY)

    except Exception as e:
        log_with_correlation("exception", f"Unexpected error during goodwill submission: {e}")
        return make_response(jsonify(status="error", error="An internal server error occurred."), http.HTTPStatus.INTERNAL_SERVER_ERROR)


