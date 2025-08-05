import logging
import json
import http
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, List, Union
import uuid

from flask import Blueprint, request, jsonify, Response
from pydantic import BaseModel, Field, ValidationError, validator, parse_obj_as
from typing_extensions import Literal

from peoples_coin.extensions import immune_system, cognitive_system, db
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import EventLog

logger = logging.getLogger(__name__)

# --- Constants ---
KEY_STATUS = "status"
KEY_ERROR = "error"
KEY_DETAILS = "details"
KEY_MESSAGE = "message"
KEY_RECEIVED_ID = "received_id"
EVENT_NERVOUS_DATA_RECEIVED = 'nervous_node_data_received'
EVENT_NERVOUS_DATA_PROCESSING_FAILED = 'nervous_node_data_processing_failed'


# ==============================================================================
# 1. Pydantic Models for Internal Node Data
# ==============================================================================

class BlockPayloadSchema(BaseModel):
    block_number: int
    block_hash: str
    transactions: List[Dict[str, Any]]

class TransactionListSchema(BaseModel):
    new_transactions: List[Dict[str, Any]]

# A Union of all possible message types. Pydantic will automatically
# select the correct model based on the 'data_type' field.
InternalNodeDataSchema = Union[
    "BlockSyncMessage",
    "TxPoolUpdateMessage"
]

class BlockSyncMessage(BaseModel):
    data_type: Literal["block_sync"]
    payload: BlockPayloadSchema
    source_node_id: Optional[str] = None
    correlation_id: Optional[str] = None

class TxPoolUpdateMessage(BaseModel):
    data_type: Literal["tx_pool_update"]
    payload: TransactionListSchema
    source_node_id: Optional[str] = None
    correlation_id: Optional[str] = None

# Update forward references after all models are defined
BlockSyncMessage.update_forward_refs()
TxPoolUpdateMessage.update_forward_refs()


# ==============================================================================
# 2. Helper: Enqueue Cognitive Event
# ==============================================================================

def _create_and_enqueue_cognitive_event(session, event_type: str, payload: dict):
    """Creates and enqueues a rich event for the Cognitive System and logs it."""
    event_payload = {
        **payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_id": str(uuid.uuid4()),
    }

    try:
        cognitive_system.enqueue_event({
            "type": event_type,
            "source": "NervousSystem",
            "payload": event_payload
        })
        log_message = f"Cognitive event '{event_type}' triggered. Payload keys: {list(payload.keys())}"
        event_log_entry = EventLog(event_type=event_type, message=log_message)
        session.add(event_log_entry)
        logger.info(f"[Nervous] Enqueued cognitive event '{event_type}' with event_id {event_payload['event_id']}")
    except Exception as e:
        logger.error(f"[Nervous] Failed to log or enqueue cognitive event '{event_type}': {e}", exc_info=True)


# ==============================================================================
# 3. Blueprint & Routes
# ==============================================================================

nervous_bp = Blueprint('nervous', __name__, url_prefix='/nervous')


def json_response(data: dict, status_code: int = http.HTTPStatus.OK) -> Tuple[Response, int]:
    """Helper for consistent JSON responses."""
    return jsonify(data), status_code


@nervous_bp.route("/status", methods=["GET"])
def nervous_status() -> Tuple[Response, int]:
    """Health check for the Nervous System."""
    logger.debug("✅ Nervous system status check called.")
    return json_response({KEY_STATUS: "success", KEY_MESSAGE: "Nervous System operational"})


@nervous_bp.route("/receive_node_data", methods=["POST"])
@immune_system.check()
def receive_node_data() -> Tuple[Response, int]:
    """Receives and processes internal data from peer nodes with strict schema validation."""
    if not request.is_json:
        logger.warning("[Nervous] Missing or invalid JSON body.")
        return json_response({KEY_STATUS: "error", KEY_ERROR: "Content-Type must be application/json"}, http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE)

    if request.content_length and request.content_length > 5_000_000:
        logger.warning("[Nervous] Payload too large.")
        return json_response({KEY_STATUS: "error", KEY_ERROR: "Payload too large"}, http.HTTPStatus.REQUEST_ENTITY_TOO_LARGE)

    raw_data = request.get_json()
    source_node_id = raw_data.get("source_node_id", "UNKNOWN")
    correlation_id = raw_data.get("correlation_id")
    
    logger.info(f"[Nervous] Received data from node: {source_node_id}, Type: {raw_data.get('data_type', 'N/A')}")

    try:
        # **IMPROVEMENT**: This single line replaces the manual if/elif block.
        # Pydantic automatically parses the data into the correct model from the Union.
        validated_data = parse_obj_as(InternalNodeDataSchema, raw_data)

        with get_session_scope() as session:
            # Business logic is now handled by checking the model's type
            if isinstance(validated_data, BlockSyncMessage):
                logger.info(f"Processing block sync from {source_node_id}, block #{validated_data.payload.block_number}")
                # TODO: Call consensus or blockchain sync logic here
            
            elif isinstance(validated_data, TxPoolUpdateMessage):
                logger.info(f"Processing tx pool update from {source_node_id}, {len(validated_data.payload.new_transactions)} txs")
                # TODO: Update transaction pool or mempool here
            
            _create_and_enqueue_cognitive_event(
                session,
                EVENT_NERVOUS_DATA_RECEIVED,
                {
                    "data_type": validated_data.data_type,
                    "source_node_id": source_node_id,
                    "correlation_id": correlation_id,
                }
            )

        logger.info(f"[Nervous] Data from node {source_node_id} processed successfully.")
        return json_response({
            KEY_STATUS: "success",
            KEY_MESSAGE: f"Data of type '{validated_data.data_type}' from node '{source_node_id}' accepted."
        }, http.HTTPStatus.ACCEPTED)

    except ValidationError as ve:
        logger.warning(f"🚫 Validation failed for internal node data: {ve.errors()}")
        with get_session_scope() as session:
            _create_and_enqueue_cognitive_event(session, EVENT_NERVOUS_DATA_PROCESSING_FAILED, {"validation_errors": ve.errors(), "source_node_id": source_node_id, "correlation_id": correlation_id})
        return json_response({KEY_STATUS: "error", KEY_ERROR: "Invalid internal data format", KEY_DETAILS: ve.errors()}, http.HTTPStatus.BAD_REQUEST)

    except Exception as e:
        logger.exception(f"💥 Unexpected error processing internal node data from {source_node_id}.")
        with get_session_scope() as session:
            _create_and_enqueue_cognitive_event(session, EVENT_NERVOUS_DATA_PROCESSING_FAILED, {"error_message": str(e), "source_node_id": source_node_id, "correlation_id": correlation_id})
        return json_response({KEY_STATUS: "error", KEY_ERROR: "Internal server error"}, http.HTTPStatus.INTERNAL_SERVER_ERROR)
