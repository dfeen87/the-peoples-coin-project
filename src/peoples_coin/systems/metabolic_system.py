# peoples_coin/peoples_coin/systems/metabolic_system.py

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from flask import Blueprint, request, jsonify
from pydantic import BaseModel, Field, ValidationError, field_validator

from ..db import db
from ..db.models import GoodwillAction
from peoples_coin.validation.validate_transaction import validate_transaction

logger = logging.getLogger(__name__)

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
def metabolic_status():
    """
    Health check endpoint for the Metabolic System.
    """
    logger.debug("Metabolic system status check called.")
    return jsonify({"status": "Metabolic System operational"}), 200


@metabolic_bp.route('/submit_goodwill', methods=['POST'])
def submit_goodwill():
    """
    Endpoint to receive, validate (schema + business rules), and queue goodwill actions.
    """
    logger.info("📥 Received goodwill submission request.")
    if not request.is_json:
        logger.warning("Request missing JSON body.")
        return jsonify({"error": "Content-Type must be application/json"}), 415

    data = request.get_json()
    if not data:
        logger.warning("Empty JSON payload.")
        return jsonify({"error": "No JSON data provided"}), 400

    try:
        # Step 1: Validate schema with Pydantic
        goodwill_data = GoodwillActionSchema(**data)
        logger.info(f"✅ Goodwill action schema validated for user_id: {goodwill_data.user_id}")

        # Step 2: Run custom business logic validation
        validated_dict = goodwill_data.dict()
        is_valid, validation_result = validate_transaction(validated_dict)
        if not is_valid:
            logger.warning(f"🚫 Business logic validation failed: {validation_result}")
            return jsonify({"error": "Transaction validation failed", "details": validation_result}), 400

        # Step 3: Persist to DB
        goodwill_action = GoodwillAction(
            user_id=validated_dict['user_id'],
            action_type=validated_dict['action_type'],
            description=validated_dict['description'],
            timestamp=validated_dict['timestamp'],
            contextual_data=validated_dict['contextual_data'],
            status='pending'
        )
        db.session.add(goodwill_action)
        db.session.commit()

        logger.info(f"💾 GoodwillAction ID {goodwill_action.id} saved with status 'pending'.")

        return jsonify({
            "message": "Goodwill action accepted and queued for processing.",
            "action_id": goodwill_action.id,
            "status": goodwill_action.status
        }), 202

    except ValidationError as ve:
        logger.warning(f"🚫 Validation failed: {ve.errors()}")
        return jsonify({"error": "Invalid data provided", "details": ve.errors()}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception("💥 Unexpected error during goodwill submission.")
        return jsonify({"error": "Internal server error"}), 500

