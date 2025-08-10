# peoples_coin/systems/nervous_system.py
import logging
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, ValidationError, parse_obj_as
from typing_extensions import Literal

from peoples_coin.extensions import cognitive_system, db
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import EventLog

logger = logging.getLogger(__name__)

# --- Pydantic Models for Internal Node Data ---

class BlockPayloadSchema(BaseModel):
    block_number: int
    block_hash: str
    transactions: List[Dict[str, Any]]

class TransactionListSchema(BaseModel):
    new_transactions: List[Dict[str, Any]]

InternalNodeDataSchema = Union["BlockSyncMessage", "TxPoolUpdateMessage"]

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

BlockSyncMessage.update_forward_refs()
TxPoolUpdateMessage.update_forward_refs()


# --- Core Logic Functions ---

def process_node_data(raw_data: dict) -> Dict[str, Any]:
    """Validates and processes incoming data from a peer node."""
    validated_data = parse_obj_as(InternalNodeDataSchema, raw_data)
    source_node_id = validated_data.source_node_id or "UNKNOWN"
    
    with get_session_scope(db) as session:
        if isinstance(validated_data, BlockSyncMessage):
            logger.info(f"Processing block sync from {source_node_id}, block #{validated_data.payload.block_number}")
            # TODO: Call consensus or blockchain sync logic here
        
        elif isinstance(validated_data, TxPoolUpdateMessage):
            logger.info(f"Processing tx pool update from {source_node_id}, {len(validated_data.payload.new_transactions)} txs")
            # TODO: Update transaction pool or mempool here
            
        # Enqueue an event for the cognitive system
        event_payload = {
            "data_type": validated_data.data_type,
            "source_node_id": source_node_id,
            "correlation_id": validated_data.correlation_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id": str(uuid.uuid4())
        }
        cognitive_system.enqueue_event({
            "type": 'nervous_node_data_received',
            "source": "NervousSystem",
            "payload": event_payload
        })
    
    return {
        "message": f"Data of type '{validated_data.data_type}' from node '{source_node_id}' accepted."
    }

# --- Functions for status page ---

def get_nervous_status() -> Dict[str, Any]:
    """Health check for the Nervous System."""
    # In a real system, you might check peer node connectivity
    return {"active": True, "healthy": True, "info": "Nervous System operational"}

def get_nervous_transaction_state(txn_id: str) -> Dict[str, Any]:
    """Placeholder for checking a transaction's nervous system state."""
    return {"state": "broadcasted", "confirmed": True}
