import json
import logging
import http
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import UUID # Import UUID for type hinting if needed

from flask import Blueprint, request, jsonify, Response
from pydantic import BaseModel, Field, ValidationError, field_validator, root_validator
from typing_extensions import Literal

from peoples_coin.db.db_utils import get_session_scope
from peoples_coin.db.models import GoodwillAction, UserAccount # Import UserAccount
from peoples_coin.validation.validate_transaction import validate_transaction # This file will need updating too
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
            # Assume UTC if no timezone is provided for simplicity, or reject.
            # Rejecting is safer for strict APIs.
            # For Firebase timestamps without explicit TZ, they are often UTC.
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    # Optional: For Pydantic V2, you might use @model_validator instead of @root_validator
    # @root_validator(pre=True)
    # def check_loves_value(cls, values):
    #    loves = values.get('loves_value')
    #    if loves is not None and not (1 <= loves <= 100):
    #        raise ValueError("Loves value must be between 1 and 100.")
    #    return values


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
    Receives, validates & persists a goodwill action, then queues it for processing.
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
        # Step 1: Pydantic schema validation for incoming data
        goodwill_data = GoodwillActionSchema(**data)
        logger.info(
            f"✅ Schema validated for user_id: {goodwill_data.user_id}, "
            f"action_type: {goodwill_data.action_type}, "
            f"loves_value: {goodwill_data.loves_value}."
        )

        # Step 2: Domain/business validation using validate_transaction
        # NOTE: The validate_transaction function in validate_transaction.py
        #       will also need to be updated to handle the new fields (like loves_value)
        #       and ensure it works with the current schema.
        validated_dict = goodwill_data.model_dump() # Use model_dump for Pydantic V2
        validation_result = validate_transaction(validated_dict) # This now returns ValidationSuccess/ValidationFailure
        if not validation_result.is_valid:
            logger.warning(
                f"🚫 Business validation failed for user_id: {goodwill_data.user_id}. "
                f"Details: {validation_result.errors}"
            )
            return jsonify(
                status="error",
                error="Transaction validation failed",
                details=validation_result.errors
            ), http.HTTPStatus.BAD_REQUEST

        # Step 3: Persist to database (GoodwillAction)
        with get_session_scope(db) as session:
            # Find the UserAccount based on the Firebase UID
            # Ensure UserAccount model has firebase_uid column
            user_account = session.query(UserAccount).filter_by(firebase_uid=goodwill_data.user_id).first()
            if not user_account:
                logger.warning(f"🚫 UserAccount not found for firebase_uid: {goodwill_data.user_id}")
                return jsonify(status="error", error="User not found"), http.HTTPStatus.BAD_REQUEST

            goodwill_action = GoodwillAction(
                performer_user_id=user_account.id, # Link to UserAccount's internal UUID PK
                action_type=goodwill_data.action_type,
                description=goodwill_data.description,
                # created_at (TimestampMixin) will be set automatically
                contextual_data=goodwill_data.contextual_data,
                loves_value=goodwill_data.loves_value,
                initial_model_state_v0=goodwill_data.initial_model_state_v0,
                expected_workload_intensity_w0=goodwill_data.expected_workload_intensity_w0,
                client_compute_estimate=goodwill_data.client_compute_estimate,
                correlation_id=goodwill_data.correlation_id,
                status=STATUS_PENDING_VERIFICATION, # Use constant for consistency
                resonance_score=goodwill_data.resonance_score # Ensure this is passed
            )
            session.add(goodwill_action)
            session.flush() # Populate goodwill_action.id (UUID) after add

            logger.info(
                f"💾 GoodwillAction ID {goodwill_action.id} "
                f"for user {goodwill_data.user_id} ({goodwill_data.action_type}, {goodwill_data.loves_value} loves) "
                f"queued with status '{STATUS_PENDING_VERIFICATION}'."
            )

            # Step 4: Queue for further async processing (e.g., blockchain issuance)
            # This is a placeholder for your messaging system (Pub/Sub, Celery, etc.)
            # Example: publish_to_message_queue(str(goodwill_action.id))
            logger.info(f"🚀 GoodwillAction ID {goodwill_action.id} queued for blockchain processing.")

            response_payload = {
                KEY_MESSAGE: "Goodwill action accepted and queued for processing.",
                KEY_ACTION_ID: str(goodwill_action.id), # Convert UUID to string for JSON response
                KEY_STATUS: STATUS_ACCEPTED,
            }
            if goodwill_action.correlation_id:
                response_payload["correlation_id"] = goodwill_action.correlation_id

        return jsonify(status="success", **response_payload), http.HTTPStatus.ACCEPTED

    except ValidationError as ve:
        logger.warning(f"🚫 Pydantic validation failed. Errors: {ve.errors()}")
        return jsonify(status="error", error="Invalid data provided", details=ve.errors()), http.HTTPStatus.BAD_REQUEST

    except Exception as e:
        logger.exception(f"💥 Unexpected error during goodwill submission: {e}")
        return jsonify(status="error", error="Internal server error", details=str(e)), http.HTTPStatus.INTERNAL_SERVER_ERROR
