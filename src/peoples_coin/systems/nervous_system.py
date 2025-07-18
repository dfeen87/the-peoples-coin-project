import logging
import json
import http
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, request, jsonify, Response
from pydantic import BaseModel, Field, ValidationError # Added Field for optional defaults

from peoples_coin.extensions import immune_system, cognitive_system, db # Removed validate_transaction
from peoples_coin.db.db_utils import get_session_scope
from peoples_coin.db.models import EventLog # DataEntry removed as it's not used here anymore

logger = logging.getLogger(__name__)

# --- Constants ---
KEY_STATUS = "status"
KEY_ERROR = "error"
KEY_DETAILS = "details"
KEY_MESSAGE = "message"
KEY_RECEIVED_ID = "received_id" # More generic ID for incoming data
EVENT_NERVOUS_DATA_RECEIVED = 'nervous_node_data_received'
EVENT_NERVOUS_DATA_PROCESSING_FAILED = 'nervous_node_data_processing_failed'


# ==============================================================================
# 1. Internal Node Data Schema (PLACEHOLDER)
#    Define specific Pydantic models for data exchanged between nodes.
#    Examples: BlockSyncMessage, TransactionPoolUpdate, PeerStatusUpdate
# ==============================================================================

class InternalNodeDataSchema(BaseModel):
    """
    Placeholder schema for internal data exchanged between nodes.
    You will replace this with specific Pydantic models like:
    - BlockSyncMessage(BaseModel): block_number: int, block_hash: str, transactions: List[Dict[str, Any]]
    - TransactionPoolUpdate(BaseModel): new_transactions: List[Dict[str, Any]]
    - PeerStatusUpdate(BaseModel): peer_id: str, status: str, last_seen: datetime
    """
    data_type: str = Field(..., description="Type of internal node data (e.g., 'block_sync', 'tx_pool_update')")
    payload: Dict[str, Any] = Field(..., description="The actual data payload from the peer node")
    source_node_id: Optional[str] = Field(None, description="ID of the node sending this data")


# ==============================================================================
# 2. Helper: Enqueue Cognitive Event
# ==============================================================================

def _create_and_enqueue_cognitive_event(session, event_type: str, payload: dict):
    """
    Helper to create and enqueue a rich event for the Cognitive System,
    and log it to the local database.
    """
    # This assumes cognitive_system has an enqueue_event method
    # and that the EventLog model is properly linked to db.session
    try:
        cognitive_system.enqueue_event({
            "type": event_type,
            "source": "NervousSystem",
            "payload": payload
        })
        log_message = f"Cognitive event '{event_type}' triggered. Payload keys: {list(payload.keys())}"
        event_log_entry = EventLog(event_type=event_type, message=log_message)
        session.add(event_log_entry)
    except Exception as e:
        logger.error(f"[Nervous] Failed to log or enqueue cognitive event '{event_type}': {e}", exc_info=True)


metabolic_bp = Blueprint('metabolic', __name__, url_prefix='/metabolic') # This blueprint should be renamed if moved

nervous_bp = Blueprint('nervous', __name__, url_prefix='/nervous')


@nervous_bp.route("/status", methods=["GET"])
def nervous_status() -> Tuple[Response, int]:
    """Health check for the Nervous System."""
    logger.debug("✅ Nervous system status check called.")
    return jsonify({KEY_STATUS: "success", KEY_MESSAGE: "Nervous System operational"}), http.HTTPStatus.OK


@nervous_bp.route("/receive_node_data", methods=["POST"]) # Renamed endpoint
@immune_system.check() # Assumed this checks internal API keys between nodes
def receive_node_data() -> Tuple[Response, int]:
    """
    Receives and processes internal data (e.g., blocks, transactions, peer status) from other nodes.
    """
    if not request.is_json:
        logger.warning("[Nervous] Missing JSON body or incorrect Content-Type.")
        return jsonify({
            KEY_STATUS: "error",
            KEY_ERROR: "Content-Type must be application/json"
        }), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    # Check payload size (optional, but good for internal communication)
    if request.content_length and request.content_length > 5_000_000: # Increased limit for larger blocks/data
        logger.warning("[Nervous] Payload too large.")
        return jsonify({
            KEY_STATUS: "error",
            KEY_ERROR: "Payload too large"
        }), http.HTTPStatus.REQUEST_ENTITY_TOO_LARGE

    data = request.get_json()
    source_node_id = data.get("source_node_id", "UNKNOWN") # Example: ID of the sending node
    logger.info(f"[Nervous] Received data from node: {source_node_id}, Type: {data.get('data_type', 'N/A')}")

    try:
        # Step 1: Validate incoming internal node data against its specific schema
        # Replace InternalNodeDataSchema with your actual schema for inter-node messages
        validated_internal_data = InternalNodeDataSchema(**data)
        logger.info(f"✅ Internal node data schema validated for type: {validated_internal_data.data_type}")

        with get_session_scope(db) as session:
            # Step 2: Process the validated internal data (e.g., sync block, update transaction pool)
            # This is where your core inter-node logic resides.
            # Example:
            if validated_internal_data.data_type == 'block_sync':
                # Call consensus system to validate and potentially add block
                # self.app.consensus.add_block_from_peer(validated_internal_data.payload)
                logger.info(f"Processing block sync data from {source_node_id}.")
                # You would add logic to verify the block and persist it
            elif validated_internal_data.data_type == 'tx_pool_update':
                # Update local transaction pool
                logger.info(f"Processing transaction pool update from {source_node_id}.")
                # You would add logic to merge transactions
            else:
                logger.warning(f"[Nervous] Unrecognized internal data type: {validated_internal_data.data_type}")
                return jsonify({
                    KEY_STATUS: "error",
                    KEY_ERROR: "Unrecognized internal data type"
                }), http.HTTPStatus.BAD_REQUEST


            _create_and_enqueue_cognitive_event(
                session,
                EVENT_NERVOUS_DATA_RECEIVED,
                {"data_type": validated_internal_data.data_type, "source_node_id": source_node_id}
            )
            logger.info(f"[Nervous] Data from node {source_node_id} processed successfully.")

        return jsonify({
            KEY_STATUS: "success",
            KEY_MESSAGE: f"Data of type '{validated_internal_data.data_type}' from node '{source_node_id}' accepted and processed."
        }), http.HTTPStatus.ACCEPTED

    except ValidationError as ve:
        logger.warning(f"🚫 Pydantic validation failed for internal node data. Errors: {ve.errors()}")
        with get_session_scope(db) as session:
            _create_and_enqueue_cognitive_event(
                session,
                EVENT_NERVOUS_DATA_PROCESSING_FAILED,
                {"validation_details": ve.errors(), "source_node_id": source_node_id}
            )
        return jsonify(status="error", error="Invalid internal data format", details=ve.errors()), http.HTTPStatus.BAD_REQUEST

    except Exception as e:
        logger.exception(f"💥 Unexpected error processing internal node data from {source_node_id}.")
        with get_session_scope(db) as session:
            _create_and_enqueue_cognitive_event(
                session,
                EVENT_NERVOUS_DATA_PROCESSING_FAILED,
                {"error_message": str(e), "source_node_id": source_node_id}
            )
        return jsonify({
            KEY_STATUS: "error",
            KEY_ERROR: "Internal server error during node data processing"
        }), http.HTTPStatus.INTERNAL_SERVER_ERROR
