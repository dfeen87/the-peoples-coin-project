import logging
import json
import http
from flask import Blueprint, request, jsonify, Response

from ..extensions import immune_system, cognitive_system, db
from ..db.db_utils import get_session_scope
from ..db.models import DataEntry, EventLog
from ..validation import validate_transaction

logger = logging.getLogger(__name__)

# --- Constants ---
KEY_STATUS = "status"
KEY_ERROR = "error"
KEY_DETAILS = "details"
KEY_MESSAGE = "message"
KEY_ENTRY_ID = "entry_id"
EVENT_NERVOUS_DATA_INGESTED = 'nervous_data_ingested'
EVENT_NERVOUS_VALIDATION_FAILED = 'nervous_validation_failed'

nervous_bp = Blueprint('nervous', __name__, url_prefix='/nervous')


def _create_and_enqueue_cognitive_event(session, event_type: str, payload: dict):
    """
    Helper to create and enqueue a rich event for the Cognitive System,
    and log it to the local database.
    """
    cognitive_system.enqueue_event({
        "type": event_type,
        "source": "NervousSystem",
        "payload": payload
    })
    try:
        log_message = f"Cognitive event '{event_type}' triggered. Payload keys: {list(payload.keys())}"
        event = EventLog(event_type=event_type, message=log_message)
        session.add(event)
    except Exception as e:
        logger.error(f"[Nervous] Failed to log event '{event_type}' to local DB: {e}", exc_info=True)


@nervous_bp.route("/status", methods=["GET"])
def nervous_status() -> tuple[Response, int]:
    """Health check for the Nervous System."""
    return jsonify({KEY_STATUS: "✅ Nervous System operational"}), http.HTTPStatus.OK


@nervous_bp.route("/process_data", methods=["POST"])
@immune_system.check()
def process_data() -> tuple[Response, int]:
    """
    Receives, validates, and stores data, creating a DataEntry and triggering cognitive events.
    """
    if not request.is_json:
        return jsonify({
            KEY_STATUS: "error",
            KEY_ERROR: "Content-Type must be application/json"
        }), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    if request.content_length and request.content_length > 1_000_000:
        return jsonify({
            KEY_STATUS: "error",
            KEY_ERROR: "Payload too large"
        }), http.HTTPStatus.REQUEST_ENTITY_TOO_LARGE

    data = request.get_json()
    transaction_id = data.get("id", "N/A")
    logger.info(f"[Nervous] Received data for processing. Transaction ID: {transaction_id}")

    try:
        is_valid, result_details = validate_transaction(data)
    except ImportError:
        logger.warning("[Nervous] validate_transaction not found — assuming valid.")
        is_valid, result_details = True, {}

    if not is_valid:
        logger.warning(f"[Nervous] Validation failed for transaction {transaction_id}: {result_details}")
        try:
            identifier = immune_system._get_identifier()
        except Exception as e:
            logger.error(f"[Nervous] Failed to get identifier from immune_system: {e}")
            identifier = "unknown"

        immune_system.record_invalid_attempt(identifier)

        with get_session_scope() as session:
            _create_and_enqueue_cognitive_event(
                session,
                EVENT_NERVOUS_VALIDATION_FAILED,
                {"validation_details": result_details, "identifier": identifier, "transaction_id": transaction_id}
            )

        return jsonify({
            KEY_STATUS: "error",
            KEY_ERROR: "Validation failed",
            KEY_DETAILS: result_details
        }), http.HTTPStatus.BAD_REQUEST

    try:
        with get_session_scope() as session:
            new_entry = DataEntry(
                value=json.dumps(data),
                processed=False
            )
            session.add(new_entry)
            session.flush()

            _create_and_enqueue_cognitive_event(
                session,
                EVENT_NERVOUS_DATA_INGESTED,
                {"entry_id": new_entry.id, "transaction_id": transaction_id}
            )

            logger.info(f"[Nervous] Data entry stored with ID: {new_entry.id}, returning 202")

            return jsonify({
                KEY_STATUS: "success",
                KEY_MESSAGE: "Data received and queued for processing",
                KEY_ENTRY_ID: new_entry.id
            }), http.HTTPStatus.ACCEPTED

    except Exception as e:
        logger.exception(f"[Nervous] Failed to process data for transaction {transaction_id}: {e}")
        return jsonify({
            KEY_STATUS: "error",
            KEY_ERROR: "Processing failed due to an internal error"
        }), http.HTTPStatus.INTERNAL_SERVER_ERROR

