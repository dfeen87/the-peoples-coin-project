import os # Re-added as requested and for general completeness
import json
import logging
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from pydantic import BaseModel, Field, ValidationError # Re-added Pydantic for validation

# Import the db instance from the main app's db module
from peoples_coin.peoples_coin.db.db import db
# Import the GoodwillAction model
from peoples_coin.peoples_coin.db.models import GoodwillAction
# Removed: from .endocrine_system import AILEEController (no longer directly called for tasks)

# Configure logging for the metabolic system
logger = logging.getLogger(__name__)

# --- Pydantic Model for Goodwill Action ---
# This defines the expected structure and validation rules for
# incoming goodwill action data.
class GoodwillActionSchema(BaseModel):
    user_id: str = Field(..., description="Unique identifier for the user performing the action.")
    action_type: str = Field(..., description="Category of the goodwill action (e.g., 'community_support', 'environmental_contribution').")
    description: str = Field(..., min_length=10, max_length=500, description="Detailed description of the goodwill action.")
    timestamp: datetime = Field(..., description="ISO 8601 formatted timestamp of when the action occurred.",
                                 examples=["2025-07-10T10:00:00Z"])
    contextual_data: dict = Field(default_factory=dict, description="Additional context or metadata about the action.")

    # Validator to ensure timestamp is in UTC and has timezone info
    # This helps maintain consistency across distributed nodes
    def model_post_init(self, __context):
        if self.timestamp.tzinfo is None:
            raise ValueError("Timestamp must include timezone information (e.g., 'Z' for UTC).")
        if self.timestamp.tzinfo != timezone.utc:
            self.timestamp = self.timestamp.astimezone(timezone.utc)


# --- Flask Blueprint for Metabolic System ---
# A Blueprint helps organize routes and other code into modular components.
# It can then be registered with the main Flask application.
metabolic_bp = Blueprint('metabolic', __name__, url_prefix='/metabolic') # Changed name back to 'metabolic' for consistency

# --- Metabolic System API Endpoints ---

@metabolic_bp.route('/', methods=['GET'])
def get_status():
    """
    Provides a basic status check for the Metabolic System.
    """
    logger.info("Metabolic System: Status check requested.")
    return jsonify({"message": "Welcome to The People's Coin Metabolic System", "status": "operational"}), 200

@metabolic_bp.route('/submit_goodwill', methods=['POST'])
def submit_goodwill(): # Renamed function for consistency with previous curl commands
    """
    Receives and validates a goodwill action from a user or another system.
    This is the ingestion pipeline for the Metabolic System.
    It now persists the action to the database with a 'pending' status for AILEE to pick up.
    """
    logger.info("Metabolic System: Goodwill submission attempt.")
    try:
        data = request.get_json()
        if not data:
            logger.warning("Metabolic System: No JSON data received for goodwill submission.")
            return jsonify({"error": "No JSON data provided"}), 400

        # Validate incoming data against the Pydantic schema
        try:
            goodwill_action_data = GoodwillActionSchema(**data)
        except ValidationError as e:
            logger.error(f"Metabolic System: Data validation error: {e.errors()}")
            return jsonify({"error": "Invalid goodwill data", "details": e.errors()}), 400

        logger.info(f"Metabolic System: Validated goodwill action for user_id: {goodwill_action_data.user_id}")

        # --- Create a GoodwillAction database object with initial pending status ---
        goodwill_action_db_obj = GoodwillAction(
            user_id=goodwill_action_data.user_id,
            action_type=goodwill_action_data.action_type,
            description=goodwill_action_data.description,
            timestamp=goodwill_action_data.timestamp,
            contextual_data=json.dumps(goodwill_action_data.contextual_data), # Store dict as JSON string
            raw_goodwill_score=0, # Initial placeholder
            resonance_score=0, # Initial placeholder
            status='pending' # Initial status for AILEE to pick up from DB
        )

        # --- Persist the GoodwillAction to the database immediately ---
        db.session.add(goodwill_action_db_obj)
        db.session.commit()
        logger.info(f"Metabolic System: Goodwill action saved to DB with ID: {goodwill_action_db_obj.id} with status 'pending'.")

        # Removed: Direct call to ailee_controller.add_task()
        # AILEE workers will now poll the database for 'pending' tasks.
        # This decouples the Metabolic System from AILEE's internal queue.
        
        # --- Return 202 Accepted response, as AILEE processing is asynchronous ---
        return jsonify({
            "message": "Goodwill action received, validated, and queued for AILEE processing. Scores will be updated asynchronously.",
            "goodwill_action_id": goodwill_action_db_obj.id, # Return the actual DB ID
            "user_id": goodwill_action_db_obj.user_id,
            "action_type": goodwill_action_db_obj.action_type,
            "status": goodwill_action_db_obj.status, # Now explicitly 'pending'
            "initial_raw_score": goodwill_action_db_obj.raw_goodwill_score, # Will be 0
            "initial_resonance_score": goodwill_action_db_obj.resonance_score # Will be 0
        }), 202 # 202 Accepted, as processing is not complete yet

    except Exception as e: # Catch all exceptions, including ValidationError and others
        db.session.rollback() # Rollback in case of any error during DB operations
        logger.exception("Metabolic System: An unexpected error occurred during goodwill submission.") # Use exception for full traceback
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


