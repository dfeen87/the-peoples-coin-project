import json
import logging
import http
from datetime import datetime, timezone
from typing import Any, Dict

from flask import Blueprint, request, jsonify, Response
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

# Assuming a db_utils file with get_session_scope exists
from ..db.db_utils import get_session_scope
from ..db.models import GoodwillAction
from peoples_coin.validation.validate_transaction import validate_transaction

# --- Logger ---
logger = logging.getLogger(__name__)

# --- Constants ---
# Centralizing constants reduces errors from typos and simplifies maintenance.
KEY_STATUS = "status"
KEY_ERROR = "error"
KEY_DETAILS = "details"
KEY_MESSAGE = "message"
KEY_ACTION_ID = "action_id"
STATUS_PENDING = 'pending'

# --- Validation Schema ---
class GoodwillActionSchema(BaseModel):
    """Schema & validation for incoming goodwill actions."""
    user_id: str = Field(..., description="Unique identifier for the user.")
    action_type: str = Field(..., description="Category/type of goodwill action.")
    description: str = Field(..., min_length=10, max_length=500, description="Detailed description of the action.")
    timestamp: datetime = Field(..., description="ISO 8601 timestamp of the action.")
    contextual_data: Dict[str, Any] = Field(default_factory=dict, description="Optional metadata/context for the action.")

    @field_validator('timestamp')
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        """Ensure timestamp is timezone-aware & converted to UTC."""
        if v.tzinfo is None:
            raise ValueError("Timestamp must include timezone information (e.g., 'Z' for UTC).")
        return v.astimezone(timezone.utc)

# --- Blueprint Definition ---
metabolic_bp = Blueprint('metabolic', __name__, url_prefix='/metabolic')


@metabolic_bp.route('/status', methods=['GET'])
def metabolic_status() -> tuple[Response, int]:
    """
    Health check endpoint for the Metabolic System.
    """
    logger.debug("Metabolic system status check called.")
    return jsonify({KEY_STATUS: "Metabolic System operational"}), http.HTTPStatus.OK


@metabolic_bp.route('/submit_goodwill', methods=['POST'])
def submit_goodwill() -> tuple[Response, int]:
    """
    Endpoint to receive, validate (schema + business rules), and queue goodwill actions.
    """
    logger.info("📥 Received goodwill submission request.")
    if not request.is_json:
        logger.warning("Request missing JSON body.")
        return jsonify({KEY_ERROR: "Content-Type must be application/json"}), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    data = request.get_json()
    if not data:
        logger.warning("Empty JSON payload.")
        return jsonify({KEY_ERROR: "No JSON data provided"}), http.HTTPStatus.BAD_REQUEST

    try:
        # Step 1: Validate schema with Pydantic
        goodwill_data = GoodwillActionSchema(**data)
        logger.info(f"✅ Goodwill action schema validated for user_id: {goodwill_data.user_id}")

        # Step 2: Run custom business logic validation
        # Use .model_dump() for Pydantic v2+ to get a dictionary
        validated_dict = goodwill_data.model_dump()
        is_valid, validation_result = validate_transaction(validated_dict)
        if not is_valid:
            logger.warning(f"🚫 Business logic validation failed: {validation_result}")
            return jsonify({KEY_ERROR: "Transaction validation failed", KEY_DETAILS: validation_result}), http.HTTPStatus.BAD_REQUEST

        # Step 3: Persist to DB within a safe, managed transaction scope
        with get_session_scope() as session:
            # Create the model instance concisely using dictionary unpacking
            goodwill_action = GoodwillAction(**validated_dict, status=STATUS_PENDING)
            session.add(goodwill_action)
            # Flush to get the ID for the response before the transaction is committed
            session.flush()

            logger.info(f"💾 GoodwillAction ID {goodwill_action.id} queued for commit with status '{STATUS_PENDING}'.")
            
            action_id = goodwill_action.id
            action_status = goodwill_action.status

        # The session is automatically committed here upon successful exit from the 'with' block.
        # If any exception occurs inside the block, the session is automatically rolled back.

        return jsonify({
            KEY_MESSAGE: "Goodwill action accepted and queued for processing.",
            KEY_ACTION_ID: action_id,
            KEY_STATUS: action_status
        }), http.HTTPStatus.ACCEPTED

    except ValidationError as ve:
        logger.warning(f"🚫 Pydantic validation failed: {ve.errors()}")
        return jsonify({KEY_ERROR: "Invalid data provided", KEY_DETAILS: ve.errors()}), http.HTTPStatus.BAD_REQUEST
    except Exception:
        # No need for db.session.rollback() as the session scope handles it.
        logger.exception("💥 Unexpected error during goodwill submission.")
        return jsonify({KEY_ERROR: "Internal server error"}), http.HTTPStatus.INTERNAL_SERVER_ERROR

