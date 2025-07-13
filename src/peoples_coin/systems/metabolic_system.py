import json
import logging
import http
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, request, jsonify, Response
from pydantic import BaseModel, Field, ValidationError, field_validator

from ..db.db_utils import get_session_scope
from ..db.models import GoodwillAction
from peoples_coin.validation.validate_transaction import validate_transaction
from peoples_coin.extensions import db

logger = logging.getLogger(__name__)

# --- Constants ---
KEY_STATUS = "status"
KEY_ERROR = "error"
KEY_DETAILS = "details"
KEY_MESSAGE = "message"
KEY_ACTION_ID = "action_id"
STATUS_PENDING = 'pending'
STATUS_ACCEPTED = 'accepted'


class GoodwillActionSchema(BaseModel):
    """
    Schema & validation for incoming goodwill actions.
    """
    user_id: str
    action_type: str
    description: str
    timestamp: datetime
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
            raise ValueError("Timestamp must include timezone information (e.g., 'Z' for UTC).")
        return v.astimezone(timezone.utc)


metabolic_bp = Blueprint('metabolic', __name__, url_prefix='/metabolic')


@metabolic_bp.route('/status', methods=['GET'])
def metabolic_status() -> Tuple[Response, int]:
    """
    Health check endpoint for the Metabolic System.
    """
    logger.debug("Metabolic system status check called.")
    return jsonify({KEY_STATUS: "Metabolic System operational"}), http.HTTPStatus.OK


@metabolic_bp.route('/submit_goodwill', methods=['POST'])
def submit_goodwill() -> Tuple[Response, int]:
    """
    Receives and validates a goodwill action, persists it, and queues it for processing.
    """
    logger.info("📥 Received goodwill submission request.")

    if not request.is_json:
        logger.warning("Request missing JSON body or incorrect Content-Type.")
        return jsonify({KEY_ERROR: "Content-Type must be application/json"}), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    data = request.get_json()
    if not data:
        logger.warning("Empty JSON payload received.")
        return jsonify({KEY_ERROR: "No JSON data provided"}), http.HTTPStatus.BAD_REQUEST

    try:
        # Step 1: Validate schema
        goodwill_data = GoodwillActionSchema(**data)
        logger.info(f"✅ Schema validated for user_id: {goodwill_data.user_id}, action_type: {goodwill_data.action_type}")

        # Step 2: Business validation
        validated_dict = goodwill_data.model_dump()
        is_valid, validation_result = validate_transaction(validated_dict)
        if not is_valid:
            logger.warning(f"🚫 Business validation failed for user_id: {goodwill_data.user_id}. Details: {validation_result}")
            return jsonify({KEY_ERROR: "Transaction validation failed", KEY_DETAILS: validation_result}), http.HTTPStatus.BAD_REQUEST

        # Step 3: Persist goodwill action to the database within a managed session scope
        with get_session_scope(db) as session:
            goodwill_action = GoodwillAction(
                **validated_dict,
                status=STATUS_PENDING,
                resonance_score=None
            )
            session.add(goodwill_action)
            session.flush()

            logger.info(
                f"💾 GoodwillAction ID {goodwill_action.id} "
                f"(Correlation ID: {goodwill_action.correlation_id}) queued with status '{STATUS_PENDING}'."
            )

            action_id = goodwill_action.id

        logger.debug(f"📤 GoodwillAction ID {action_id} queued for background processing.")

        return jsonify({
            KEY_MESSAGE: "Goodwill action accepted and queued for processing.",
            KEY_ACTION_ID: action_id,
            KEY_STATUS: STATUS_ACCEPTED
        }), http.HTTPStatus.ACCEPTED

    except ValidationError as ve:
        logger.warning(f"🚫 Pydantic validation failed. Errors: {ve.errors()}")
        return jsonify({KEY_ERROR: "Invalid data provided", KEY_DETAILS: ve.errors()}), http.HTTPStatus.BAD_REQUEST

    except Exception as e:
        logger.exception(f"💥 Unexpected error during goodwill submission: {e}")
        return jsonify({KEY_ERROR: "Internal server error", KEY_DETAILS: str(e)}), http.HTTPStatus.INTERNAL_SERVER_ERROR

