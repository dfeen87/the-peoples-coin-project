# peoples_coin/peoples_coin/systems/nervous_system.py

import logging
import json
from flask import Blueprint, request, jsonify

from ..db import db
from ..db.db_utils import get_session_scope
from ..db.models import DataEntry, EventLog
from ..validation import validate_transaction

logger = logging.getLogger(__name__)

# --- Blueprint Definition ---
nervous_bp = Blueprint('nervous', __name__, url_prefix='/nervous')


def log_event(session, event_type: str, message: str):
    """
    Logs an event to the EventLog table using the provided session.
    """
    try:
        event = EventLog(event_type=event_type, message=message)
        session.add(event)
    except Exception as e:
        logger.error(f"[Nervous] Failed to log event '{event_type}': {e}")


@nervous_bp.route("/status", methods=["GET"])
def nervous_status():
    """
    Health check for the Nervous System.
    """
    return jsonify({"status": "✅ Nervous System operational"}), 200


@nervous_bp.route("/process_data", methods=["POST"])
def process_data():
    """
    Receives, validates, and stores data, creating a DataEntry for AILEE to process.
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 415

    data = request.get_json()
    logger.info(f"[Nervous] Received data for processing: {data}")

    # Validate incoming data
    is_valid, result_details = validate_transaction(data)
    if not is_valid:
        logger.warning(f"[Nervous] Validation failed: {result_details}")
        return jsonify({"error": "Validation failed", "details": result_details}), 400

    try:
        with get_session_scope() as session:
            # Create a new DataEntry
            new_entry = DataEntry(
                value=json.dumps(data),
                processed=False
            )
            session.add(new_entry)

            # Log the ingestion event
            log_event(
                session=session,
                event_type='nervous_data_ingested',
                message=f"Nervous System stored new data entry with ID: {new_entry.id}"
            )

            logger.info(f"[Nervous] Data entry stored with ID: {new_entry.id}")

            return jsonify({
                "message": "Data received and queued for processing",
                "entry_id": new_entry.id
            }), 202  # 202 Accepted for async processing

    except Exception as e:
        logger.exception("[Nervous] Failed to process data.")
        return jsonify({"error": "Processing failed due to an internal error"}), 500

