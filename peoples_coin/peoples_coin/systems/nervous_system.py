# peoples_coin/peoples_coin/systems/nervous_system.py

import logging
import json
from flask import Blueprint, request, jsonify, current_app

# --- Import shared components ---
from ..db import db
from ..db.models import DataEntry, EventLog
from ..validation import validate_transaction
# The immune_check decorator can be imported if you want to apply it here
# from .immune_system import immune_check

logger = logging.getLogger(__name__)

# --- Blueprint Definition ---
# This blueprint will be registered with the main Flask app
nervous_bp = Blueprint('nervous', __name__, url_prefix='/nervous')

# ===== Helper Function =====
def log_event(event_type: str, message: str):
    """Logs an event to the shared database."""
    try:
        event = EventLog(event_type=event_type, message=message)
        db.session.add(event)
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to log event '{event_type}': {e}")
        db.session.rollback()

# ===== Routes for Nervous System =====

@nervous_bp.route("/status", methods=["GET"])
def nervous_status():
    """Health check for the Nervous System component."""
    # Note: AILEE status would be checked via the main app's status endpoint, not here.
    return jsonify({"status": "Nervous System operational"}), 200

@nervous_bp.route("/process_data", methods=["POST"])
# @immune_check  # You could apply your security decorator here
# @limiter.limit("5 per minute") # Rate limiting would be applied in the main app factory
def process_data():
    """
    Receives, validates, and stores data, creating a DataEntry for AILEE to process.
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 415

    data = request.get_json()
    logger.info(f"Nervous System received data for processing: {data}")

    try:
        # Assuming validate_transaction is a function that checks the data
        is_valid, result_details = validate_transaction(data)
        if not is_valid:
            return jsonify({"error": "Validation failed", "details": result_details}), 400

        # Create a new DataEntry to be processed by the main AILEE worker
        new_entry = DataEntry(
            value=json.dumps(data),
            processed=False # Mark as unprocessed for the worker
        )
        db.session.add(new_entry)
        db.session.commit()

        log_event(
            event_type='nervous_data_ingested',
            message=f"Nervous System stored new data entry with ID: {new_entry.id}"
        )

        return jsonify({
            "message": "Data received and queued for processing",
            "entry_id": new_entry.id
        }), 202 # 202 Accepted, as processing is asynchronous

    except Exception as e:
        logger.exception("Nervous System failed to process data.")
        db.session.rollback()
        return jsonify({"error": "Processing failed due to an internal error"}), 500

# To integrate this, you would add the following to your main create_app() in run.py:
#
# from .systems.nervous_system import nervous_bp
# app.register_blueprint(nervous_bp)
# logger.info("Nervous System blueprint registered.")
