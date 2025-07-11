# peoples_coin/peoples_coin/systems/metabolic_system.py

import json
import logging
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify

# Use field_validator for more declarative validation
from pydantic import BaseModel, Field, ValidationError, field_validator

from peoples_coin.peoples_coin.db.db import db
from peoples_coin.peoples_coin.db.models import GoodwillAction

logger = logging.getLogger(__name__)

class GoodwillActionSchema(BaseModel):
    """Defines the structure and validation for incoming goodwill actions."""
    user_id: str = Field(..., description="Unique identifier for the user.")
    action_type: str = Field(..., description="Category of the action.")
    description: str = Field(..., min_length=10, max_length=500, description="Detailed description.")
    timestamp: datetime = Field(..., description="ISO 8601 timestamp of the action.")
    contextual_data: dict = Field(default_factory=dict, description="Additional metadata.")

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp_is_utc(cls, v: datetime) -> datetime:
        """Ensures the timestamp is timezone-aware and converts it to UTC if necessary."""
        if v.tzinfo is None:
            raise ValueError("Timestamp must include timezone information (e.g., 'Z' for UTC).")
        if v.tzinfo != timezone.utc:
            return v.astimezone(timezone.utc)
        return v

metabolic_bp = Blueprint('metabolic', __name__, url_prefix='/metabolic')

@metabolic_bp.route('/status', methods=['GET'])
def get_status():
    """Provides a basic status check for the Metabolic System."""
    return jsonify({"message": "Metabolic System is operational."}), 200

@metabolic_bp.route('/submit_goodwill', methods=['POST'])
def submit_goodwill():
    """
    Receives, validates, and persists a goodwill action to the database with a
    'pending' status for asynchronous processing by AILEE.
    """
    logger.info("Received goodwill submission request.")
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400

    try:
        # Validate incoming data against the Pydantic schema
        goodwill_data = GoodwillActionSchema(**data)
        logger.info(f"Validated goodwill action for user_id: {goodwill_data.user_id}")

        # Create a GoodwillAction database object
        goodwill_action = GoodwillAction(
            user_id=goodwill_data.user_id,
            action_type=goodwill_data.action_type,
            description=goodwill_data.description,
            timestamp=goodwill_data.timestamp,
            # RECOMMENDED: Pass the dictionary directly. SQLAlchemy's JSON type handles serialization.
            contextual_data=goodwill_data.contextual_data,
            status='pending' # Initial status for the worker to pick up
        )

        db.session.add(goodwill_action)
        db.session.commit()
        logger.info(f"Goodwill action ID: {goodwill_action.id} saved to DB with status 'pending'.")

        # Return a 202 Accepted response
        return jsonify({
            "message": "Goodwill action accepted and queued for processing.",
            "action_id": goodwill_action.id,
            "status": goodwill_action.status
        }), 202

    except ValidationError as e:
        logger.warning(f"Goodwill submission failed validation: {e.errors()}")
        return jsonify({"error": "Invalid data provided", "details": e.errors()}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception("An unexpected error occurred during goodwill submission.")
        return jsonify({"error": "An internal server error occurred."}), 500
