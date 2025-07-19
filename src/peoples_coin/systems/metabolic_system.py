import logging
import http
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, Union

from flask import Blueprint, request, jsonify, make_response, Response, g
from pydantic import BaseModel, Field, ValidationError, field_validator
from typing_extensions import Literal

from peoples_coin.services.goodwill_service import goodwill_service
from peoples_coin.utils.validation.exceptions import UserNotFoundError  # hypothetical custom exception
from peoples_coin.utils.validation.schemas import GoodwillActionSchema  # hypothetically moved to shared schema
from peoples_coin.constants import GoodwillStatus, ApiResponseStatus  # hypothetical enum/constants module

logger = logging.getLogger(__name__)

metabolic_bp = Blueprint('metabolic', __name__, url_prefix='/metabolic')


# Utility: Add correlation ID to logs if available
def log_with_correlation(level: str, message: str, **kwargs) -> None:
    correlation_id = getattr(g, "correlation_id", None)
    prefix = f"[CorrelationID: {correlation_id}] " if correlation_id else ""
    getattr(logger, level)(prefix + message, **kwargs)


@metabolic_bp.before_request
def extract_correlation_id() -> None:
    # Extract correlation ID from headers or generate one
    correlation_id = request.headers.get("X-Correlation-ID")
    if not correlation_id:
        import uuid
        correlation_id = str(uuid.uuid4())
    g.correlation_id = correlation_id


@metabolic_bp.route('/status', methods=['GET'])
def metabolic_status() -> Tuple[Response, int]:
    """
    Health check endpoint for the Metabolic System.
    """
    log_with_correlation("debug", "Metabolic system status check called.")
    return make_response(jsonify(status=ApiResponseStatus.SUCCESS, message="Metabolic System operational"), http.HTTPStatus.OK)


@metabolic_bp.route('/submit_goodwill', methods=['POST'])
def submit_goodwill() -> Tuple[Response, int]:
    """
    Receives goodwill action, validates & delegates to goodwill_service for processing.
    """
    log_with_correlation("info", "Received goodwill submission request.")

    if not request.is_json:
        log_with_correlation("warning", "Missing JSON body or incorrect Content-Type.")
        return make_response(jsonify(status=ApiResponseStatus.ERROR, error="Content-Type must be application/json"), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE)

    data = request.get_json(silent=True)
    if not data:
        log_with_correlation("warning", "Empty or malformed JSON payload.")
        return make_response(jsonify(status=ApiResponseStatus.ERROR, error="No valid JSON data provided"), http.HTTPStatus.BAD_REQUEST)

    try:
        # Validate incoming data early for immediate feedback
        action_data = GoodwillActionSchema(**data)

        # Delegate to service (assumed returns (bool, dict))
        success, result = goodwill_service.submit_and_queue_goodwill_action(action_data.dict())

        if success:
            response_payload = {
                "message": "Goodwill action accepted and queued for processing.",
                "action_id": result.get("action_id"),
                "status": GoodwillStatus.ACCEPTED,
            }
            if correlation_id := result.get("correlation_id"):
                response_payload["correlation_id"] = correlation_id

            log_with_correlation("info", f"GoodwillAction ID {response_payload['action_id']} accepted and queued.")
            return make_response(jsonify(status=ApiResponseStatus.SUCCESS, **response_payload), http.HTTPStatus.ACCEPTED)

        else:
            error_msg = result.get("error", "Unknown error")
            details = result.get("details", result)
            status_code = http.HTTPStatus.BAD_REQUEST

            if error_msg == "User not found":
                status_code = http.HTTPStatus.NOT_FOUND
            elif "Database error" in error_msg:
                status_code = http.HTTPStatus.INTERNAL_SERVER_ERROR

            log_with_correlation("warning", f"Goodwill action submission failed: {error_msg}. Details: {details}")
            return make_response(jsonify(status=ApiResponseStatus.ERROR, error=error_msg, details=details), status_code)

    except ValidationError as ve:
        log_with_correlation("warning", f"Pydantic validation failed: {ve.errors()}")
        return make_response(jsonify(status=ApiResponseStatus.ERROR, error="Invalid data format provided", details=ve.errors()), http.HTTPStatus.BAD_REQUEST)

    except UserNotFoundError as unfe:
        log_with_correlation("warning", f"User not found error: {unfe}")
        return make_response(jsonify(status=ApiResponseStatus.ERROR, error="User not found"), http.HTTPStatus.NOT_FOUND)

    except Exception as e:
        log_with_correlation("exception", f"Unexpected error during goodwill submission: {e}")
        return make_response(jsonify(status=ApiResponseStatus.ERROR, error="Internal server error", details=str(e)), http.HTTPStatus.INTERNAL_SERVER_ERROR)

