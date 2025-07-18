import json
import logging
import http
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, Union

from flask import Blueprint, request, jsonify, Response
from pydantic import BaseModel, Field, ValidationError, field_validator # Ensure all needed imports
from typing_extensions import Literal

# Import the service instance
from peoples_coin.services.goodwill_service import goodwill_service

# Original imports remain
from peoples_coin.db.db_utils import get_session_scope
from peoples_coin.db.models import GoodwillAction, UserAccount # Keep these imports if still needed for schema reference, or remove if only service interacts
from peoples_coin.validation.validate_transaction import validate_transaction # Keep for now if goodwill_service still uses it internally
from peoples_coin.extensions import db

logger = logging.getLogger(__name__)

# --- Constants ---
KEY_STATUS = "status"
KEY_ERROR = "error"
KEY_DETAILS = "details"
KEY_MESSAGE = "message"
KEY_ACTION_ID = "action_id"

# Align these with GoodwillAction.status values from models.py
STATUS_PENDING_VERIFICATION = 'PENDING_VERIFICATION'
STATUS_ACCEPTED = 'ACCEPTED' # For API response, not DB status

class GoodwillActionSchema(BaseModel):
    """
    Schema & validation for incoming goodwill actions.
    Aligns with GoodwillAction model fields that are submitted by client.
    """
    user_id: str # This is the Firebase UID from the frontend
    action_type: str
    description: str
    timestamp: datetime
    loves_value: int = Field(..., ge=1, le=100, description="Value of goodwill action (1-100 loves)")
    contextual_data: Dict[str, Any] = Field(default_factory=dict)
    initial_model_state_v0: Optional[float] = None
    expected_workload_intensity_w0: Optional[float] = None
    client_compute_estimate: Optional[float] = None
    correlation_id: Optional[str] = None

    @field_validator('timestamp')
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        """Ensure timestamp is timezone-aware & converted to UTC."""
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


metabolic_bp = Blueprint('metabolic', __name__, url_prefix='/metabolic')


@metabolic_bp.route('/status', methods=['GET'])
def metabolic_status() -> Tuple[Response, int]:
    """
    Health check endpoint for the Metabolic System.
    """
    logger.debug("✅ Metabolic system status check called.")
    return jsonify(status="success", message="Metabolic System operational"), http.HTTPStatus.OK


@metabolic_bp.route('/submit_goodwill', methods=['POST'])
def submit_goodwill() -> Tuple[Response, int]:
    """
    Receives raw goodwill action, validates & delegates to GoodwillService for persistence & queuing.
    """
    logger.info("📥 Received goodwill submission request.")

    if not request.is_json:
        logger.warning("❌ Missing JSON body or incorrect Content-Type.")
        return jsonify(status="error", error="Content-Type must be application/json"), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    data = request.get_json()
    if not data:
        logger.warning("❌ Empty JSON payload.")
        return jsonify(status="error", error="No JSON data provided"), http.HTTPStatus.BAD_REQUEST

    try:
        # Pydantic schema validation for incoming data
        # No need to validate here, as goodwill_service does it, but can be left for immediate feedback
        GoodwillActionSchema(**data) # Quick check, full validation is in service

        # Delegate the processing, validation, persistence, and queuing to the service layer
        success, result = goodwill_service.submit_and_queue_goodwill_action(data)

        if success:
            action_id = result.get(KEY_ACTION_ID)
            response_payload = {
                KEY_MESSAGE: "Goodwill action accepted and queued for processing.",
                KEY_ACTION_ID: action_id,
                KEY_STATUS: STATUS_ACCEPTED,
            }
            if result.get("correlation_id"):
                response_payload["correlation_id"] = result["correlation_id"]
            
            logger.info(f"📤 API: GoodwillAction ID {action_id} accepted & queued successfully.")
            return jsonify(status="success", **response_payload), http.HTTPStatus.ACCEPTED
        else:
            logger.warning(f"🚫 API: Goodwill action submission failed. Details: {result}")
            error_msg = result.get("error", "Unknown error")
            details = result.get("details", result) # Pass details from service if available
            status_code = http.HTTPStatus.BAD_REQUEST # Default to Bad Request for validation/user errors
            if error_msg == "User not found":
                status_code = http.HTTPStatus.NOT_FOUND
            elif "Database error" in error_msg:
                status_code = http.HTTPStatus.INTERNAL_SERVER_ERROR

            return jsonify(status="error", error=error_msg, details=details), status_code

    except ValidationError as ve:
        logger.warning(f"🚫 API: Pydantic validation failed for incoming payload. Errors: {ve.errors()}")
        return jsonify(status="error", error="Invalid data format provided", details=ve.errors()), http.HTTPStatus.BAD_REQUEST

    except Exception as e:
        logger.exception(f"💥 API: Unexpected error during goodwill submission: {e}")
        return jsonify(status="error", error="Internal server error", details=str(e)), http.HTTPStatus.INTERNAL_SERVER_ERROR
