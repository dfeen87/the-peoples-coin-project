import logging
import json
import http
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, List, Union
import uuid

from flask import Blueprint, request, jsonify, Response
from pydantic import BaseModel, Field, ValidationError, validator
from typing_extensions import Literal

from peoples_coin.extensions import immune_system, cognitive_system, db
from peoples_coin.db.db_utils import get_session_scope
from peoples_coin.db.models import EventLog

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
# 1. Define Strong Typed Pydantic Models for Internal Node Data
# ==============================================================================

class BlockPayloadSchema(BaseModel):
    block_number: int
    block_hash: str
    transactions: List[Dict[str, Any]]


class TransactionListSchema(BaseModel):
    new_transactions: List[Dict[str, Any]]


class InternalNodeDataBase(BaseModel):
    data_type: str = Field(..., description="Type of internal node data")
    payload: Dict[str, Any] = Field(..., description="Payload data")
    source_node_id: Optional[str] = Field(None, description="ID of source node")
    correlation_id: Optional[str] = Field(None, description="Optional correlation ID for tracing")

    @validator("data_type")
    def data_type_must_be_known(cls, v):
        allowed_types = {"block_sync", "tx_pool_update"}
        if v not in allowed_types:
            raise ValueError(f"data_type must be one of {allowed_types}")
        return v


class BlockSyncMessage(InternalNodeDataBase):
    data_type: Literal["block_sync"]
    payload: BlockPayloadSchema


class TxPoolUpdateMessage(InternalNodeDataBase):
    data_type: Literal["tx_pool_update"]
    payload: TransactionListSchema


InternalNodeDataSchema = Union[BlockSyncMessage, TxPoolUpdateMessage]


# ==============================================================================
# 2. Helper: Enqueue Cognitive Event with rich metadata
# ==============================================================================

def _create_and_enqueue_cognitive_event(session, event_type: str, payload: dict):
    """
    Create and enqueue a rich event for the Cognitive System and log it locally.
    Adds timestamps and correlation_id if present.
    """
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
@immune_system.check()  # Security decorator for internal nodes
def receive_node_data() -> Tuple[Response, int]:
    """
    Receives and processes internal data from peer nodes with strict schema validation.
    Supports multiple message types with strict payload validation.
    """

    if not request.is_json:
        logger.warning("[Nervous] Missing or invalid JSON body.")
        return json_response({
            KEY_STATUS: "error",
            KEY_ERROR: "Content-Type must be application/json"
        }, http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE)

    if request.content_length and request.content_length > 5_000_000:
        logger.warning("[Nervous] Payload too large.")
        return json_response({
            KEY_STATUS: "error",
            KEY_ERROR: "Payload too large"
        }, http.HTTPStatus.REQUEST_ENTITY_TOO_LARGE)

    raw_data = request.get_json()
    source_node_id = raw_data.get("source_node_id", "UNKNOWN")
    correlation_id = raw_data.get("correlation_id")

    logger.info(f"[Nervous] Received data from node: {source_node_id}, Type: {raw_data.get('data_type', 'N/A')}")

    # Validate against appropriate schema dynamically
    try:
        data_type = raw_data.get("data_type")
        if data_type == "block_sync":
            validated_data = BlockSyncMessage(**raw_data)
        elif data_type == "tx_pool_update":
            validated_data = TxPoolUpdateMessage(**raw_data)
        else:
            raise ValidationError([{
                "loc": ("data_type",),
                "msg": f"Unsupported data_type '{data_type}'",
                "type": "value_error"
            }], model=InternalNodeDataBase)

        with get_session_scope(db) as session:
            # TODO: Add your business logic here for each data_type
            if data_type == "block_sync":
                logger.info(f"Processing block sync from {source_node_id}, block #{validated_data.payload.block_number}")
                # Call consensus or blockchain sync logic here
                
            elif data_type == "tx_pool_update":
                logger.info(f"Processing transaction pool update from {source_node_id}, {len(validated_data.payload.new_transactions)} txs")
                # Update transaction pool or mempool here
                
            _create_and_enqueue_cognitive_event(
                session,
                EVENT_NERVOUS_DATA_RECEIVED,
                {
                    "data_type": data_type,
                    "source_node_id": source_node_id,
                    "correlation_id": correlation_id,
                }
            )

        logger.info(f"[Nervous] Data from node {source_node_id} processed successfully.")
        return json_response({
            KEY_STATUS: "success",
            KEY_MESSAGE: f"Data of type '{data_type}' from node '{source_node_id}' accepted and processed."
        }, http.HTTPStatus.ACCEPTED)

    except ValidationError as ve:
        logger.warning(f"🚫 Validation failed for internal node data: {ve.errors()}")
        with get_session_scope(db) as session:
            _create_and_enqueue_cognitive_event(
                session,
                EVENT_NERVOUS_DATA_PROCESSING_FAILED,
                {
                    "validation_errors": ve.errors(),
                    "source_node_id": source_node_id,
                    "correlation_id": correlation_id
                }
            )
        return json_response({
            KEY_STATUS: "error",
            KEY_ERROR: "Invalid internal data format",
            KEY_DETAILS: ve.errors()
        }, http.HTTPStatus.BAD_REQUEST)

    except Exception as e:
        logger.exception(f"💥 Unexpected error processing internal node data from {source_node_id}.")
        with get_session_scope(db) as session:
            _create_and_enqueue_cognitive_event(
                session,
                EVENT_NERVOUS_DATA_PROCESSING_FAILED,
                {
                    "error_message": str(e),
                    "source_node_id": source_node_id,
                    "correlation_id": correlation_id
                }
            )
        return json_response({
            KEY_STATUS: "error",
            KEY_ERROR: "Internal server error during node data processing"
        }, http.HTTPStatus.INTERNAL_SERVER_ERROR)

