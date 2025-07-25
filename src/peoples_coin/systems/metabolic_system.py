# src/peoples_coin/routes/metabolic_routes.py (example new name)

import logging
import http
import uuid

from flask import Blueprint, request, jsonify, make_response, Response, g

# Assuming these are defined in your project structure
from peoples_coin.services.goodwill_service import goodwill_service, GoodwillSubmissionError
from peoples_coin.utils.auth import require_firebase_token # Example security
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


# --- API Routes ---

@metabolic_bp.route('/status', methods=['GET'])
def metabolic_status() -> Tuple[Response, int]:
    """Health check endpoint for the Metabolic System."""
    log_with_correlation("debug", "Metabolic system status check called.")
    return make_response(jsonify(status="success", message="Metabolic System operational"), http.HTTPStatus.OK)


@metabolic_bp.route('/submit_goodwill', methods=['POST'])
@require_firebase_token # Secure this public-facing endpoint
def submit_goodwill() -> Tuple[Response, int]:
    """
    Receives a goodwill action, validates it, and delegates to the service layer
    for asynchronous processing.
    """
    log_with_correlation("info", "Received goodwill submission request.")

    if not request.is_json:
        log_with_correlation("warning", "Request missing JSON body or has incorrect Content-Type.")
        return make_response(jsonify(status="error", error="Content-Type must be application/json"), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE)

    try:
        # 1. Validate the incoming data structure
        action_data = GoodwillActionSchema(**request.get_json())
        
        # 2. Add the authenticated user's ID to the data
        #    The decorator `require_firebase_token` places the user object on `g`.
        action_data.performer_user_id = g.user.id

        # 3. Delegate to the service layer for processing
        result = goodwill_service.submit_and_queue_goodwill_action(action_data)
        
        log_with_correlation("info", f"GoodwillAction ID {result['action_id']} accepted and queued.")

        # 4. Return a success response
        return make_response(jsonify(
            status="success",
            message="Goodwill action accepted and queued for processing.",
            action_id=result.get("action_id"),
            status_code=http.HTTPStatus.ACCEPTED.value # Use value for consistency
        ), http.HTTPStatus.ACCEPTED)

    except ValidationError as ve:
        log_with_correlation("warning", f"Pydantic validation failed: {ve.errors()}")
        return make_response(jsonify(status="error", error="Invalid data format provided", details=ve.errors()), http.HTTPStatus.BAD_REQUEST)

    except UserNotFoundError as unfe:
        # This block catches the specific exception raised by the service layer.
        log_with_correlation("warning", f"User not found during goodwill submission: {unfe}")
        return make_response(jsonify(status="error", error="User specified in action not found."), http.HTTPStatus.NOT_FOUND)

    except GoodwillSubmissionError as gse:
        # A generic, expected business logic error from the service.
        log_with_correlation("error", f"A known submission error occurred: {gse}")
        return make_response(jsonify(status="error", error=str(gse)), http.HTTPStatus.UNPROCESSABLE_ENTITY)

    except Exception as e:
        # A catch-all for any other unexpected errors.
        log_with_correlation("exception", f"Unexpected error during goodwill submission: {e}")
        return make_response(jsonify(status="error", error="An internal server error occurred."), http.HTTPStatus.INTERNAL_SERVER_ERROR)
