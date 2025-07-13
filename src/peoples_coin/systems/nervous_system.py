import logging
import json
import http
from flask import Blueprint, request, jsonify, Response, current_app
from sqlalchemy.orm import Session

# --- System Imports ---
# Import the instances of the other systems, assuming they are created
# in your main app factory file (e.g., __init__.py or app.py)
from . import immune_system, cognitive_system
from ..db.db_utils import get_session_scope
from ..db.models import DataEntry, EventLog
from ..validation import validate_transaction

# --- Logger ---
logger = logging.getLogger(__name__)

# --- Constants ---
KEY_STATUS = "status"
KEY_ERROR = "error"
KEY_DETAILS = "details"
KEY_MESSAGE = "message"
KEY_ENTRY_ID = "entry_id"
EVENT_NERVOUS_DATA_INGESTED = 'nervous_data_ingested'
EVENT_NERVOUS_VALIDATION_FAILED = 'nervous_validation_failed'

# --- Blueprint Definition ---
nervous_bp = Blueprint('nervous', __name__, url_prefix='/nervous')


def _create_and_enqueue_cognitive_event(session: Session, event_type: str, payload: dict):
    """
    Helper to create a rich event and enqueue it into the Cognitive System.
    It also logs the event to the local SQL EventLog for redundancy.
    """
    # 1. Enqueue the rich event for the Cognitive System's long-term memory
    cognitive_system.enqueue_event({
        "type": event_type,
        "source": "NervousSystem",
        "payload": payload
    })

    # 2. Log a simpler version to the local EventLog table for immediate diagnostics
    try:
        log_message = f"Cognitive event '{event_type}' triggered. Payload keys: {list(payload.keys())}"
        event = EventLog(event_type=event_type, message=log_message)
        session.add(event)
    except Exception as e:
        logger.error(f"[Nervous] Failed to log event '{event_type}' to local DB. Reason: {e}")


@nervous_bp.route("/status", methods=["GET"])
def nervous_status() -> tuple[Response, int]:
    """Health check for the Nervous System."""
    return jsonify({KEY_STATUS: "✅ Nervous System operational"}), http.HTTPStatus.OK


@nervous_bp.route("/process_data", methods=["POST"])
@immune_system.check() # INTEGRATION: Protect this endpoint with the Immune System
def process_data() -> tuple[Response, int]:
    """
    Receives, validates, and stores data, creating a DataEntry for AILEE to process.
    This endpoint is protected by rate-limiting and blacklisting.
    """
    if not request.is_json:
        return jsonify({KEY_ERROR: "Content-Type must be application/json"}), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    data = request.get_json()
    transaction_id = data.get("id", "N/A")
    logger.info(f"[Nervous] Received data for processing. Transaction ID: {transaction_id}")

    # Validate incoming data
    is_valid, result_details = validate_transaction(data)
    if not is_valid:
        logger.warning(f"[Nervous] Validation failed for transaction {transaction_id}: {result_details}")
        
        # INTEGRATION: Record the failed attempt with the Immune System
        identifier = immune_system._get_identifier()
        immune_system.record_invalid_attempt(identifier)
        
        # INTEGRATION: Create a cognitive event for the failed validation
        with get_session_scope() as session:
            _create_and_enqueue_cognitive_event(
                session,
                EVENT_NERVOUS_VALIDATION_FAILED,
                {"validation_details": result_details, "identifier": identifier, "transaction_id": transaction_id}
            )
            
        return jsonify({KEY_ERROR: "Validation failed", KEY_DETAILS: result_details}), http.HTTPStatus.BAD_REQUEST

    try:
        with get_session_scope() as session:
            new_entry = DataEntry(
                value=json.dumps(data),
                processed=False
            )
            session.add(new_entry)
            session.flush() # Assign an ID to new_entry

            # INTEGRATION: Create a cognitive event for the successful ingestion
            _create_and_enqueue_cognitive_event(
                session,
                EVENT_NERVOUS_DATA_INGESTED,
                {"entry_id": new_entry.id, "transaction_id": transaction_id}
            )

            logger.info(f"[Nervous] Data entry stored with ID: {new_entry.id}")

            return jsonify({
                KEY_MESSAGE: "Data received and queued for processing",
                KEY_ENTRY_ID: new_entry.id
            }), http.HTTPStatus.ACCEPTED

    except Exception:
        logger.exception("[Nervous] Failed to process data.")
        return jsonify({KEY_ERROR: "Processing failed due to an internal error"}), http.HTTPStatus.INTERNAL_SERVER_ERROR

