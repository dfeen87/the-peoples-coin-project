# peoples_coin/systems/blockchain_system.py
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set

import requests
from requests.adapters import HTTPAdapter, Retry

try:
    from redis import Redis
except ImportError:
    Redis = None

from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models import ChainBlock, LedgerEntry, UserAccount

logger = logging.getLogger(__name__)
TRANSACTION_POOL_KEY = "blockchain:transaction_pool"

# --- Helper Functions ---
def sha256(data: bytes) -> str:
    """Computes a SHA256 hash."""
    return hashlib.sha256(data).hexdigest()

def merkle_root_hash(transactions: List[Dict[str, Any]]) -> str:
    """Computes a Merkle root hash for a list of transaction dictionaries."""
    if not transactions:
        return sha256(b'')
    txn_hashes = [sha256(json.dumps(tx, sort_keys=True).encode()) for tx in transactions]
    while len(txn_hashes) > 1:
        if len(txn_hashes) % 2 != 0:
            txn_hashes.append(txn_hashes[-1])
        txn_hashes = [sha256((txn_hashes[i] + txn_hashes[i+1]).encode()) for i in range(0, len(txn_hashes), 2)]
    return txn_hashes[0]

# --- Main Class ---
class BlockchainSystem:
    """Manages the blockchain, transaction pool, and node synchronization."""

    def __init__(self):
        self.nodes: Set[str] = set()
        self.app = None
        self.db = None
        self.redis: Optional[Redis] = None
        self._initialized = False
        logger.info("✅ BlockchainSystem instance created.")

    def init_app(self, app: Any, db_instance: Any, redis_instance: Optional[Redis]):
        """Initializes the system with app context and dependencies."""
        if self._initialized:
            return
        self.app = app
        self.db = db_instance
        self.redis = redis_instance
        if not self.redis:
            raise RuntimeError("Redis is required for the transaction pool.")
        self._initialized = True
        logger.info("🚀 BlockchainSystem initialized.")

    def add_transaction(self, transaction: Dict[str, Any]) -> int:
        """Adds a transaction to the shared transaction pool in Redis."""
        self.redis.rpush(TRANSACTION_POOL_KEY, json.dumps(transaction))
        logger.info(f"➕ Transaction added to Redis pool.")
        
        with get_session_scope(self.db) as session:
            last_block_height = session.query(ChainBlock.height).order_by(ChainBlock.height.desc()).scalar()
            return (last_block_height + 1) if last_block_height is not None else 0

    # ... [All other methods from your original Consensus class would go here] ...
    # e.g., new_block, replace_chain, _recalculate_all_user_balances, last_block, etc.


# Singleton instance
blockchain_system = BlockchainSystem()

# --- Function for status page ---
def get_blockchain_status():
    """Returns the current operational status of the blockchain interface."""
    if blockchain_system._initialized:
        return {"active": True, "healthy": True, "info": "Blockchain system operational"}
    else:
        return {"active": False, "healthy": False, "info": "Blockchain system not initialized"}
