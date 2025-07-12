"""
consensus.py
Implements the core consensus and blockchain logic for The People's Coin.
This version is designed to be backed by a database for robust state management.
"""

import json
import threading
import time
import logging
from typing import List, Dict, Optional
import hashlib

from peoples_coin.peoples_coin.db import db
from peoples_coin.peoples_coin.db.models import ChainBlock, ConsensusNode

logger = logging.getLogger(__name__)

class Block:
    """Represents a single block in the blockchain. This is a data structure, not a DB model."""
    def __init__(
        self,
        index: int,
        timestamp: float,
        transactions: List[Dict],
        previous_hash: str,
        nonce: int = 0,
        block_hash: Optional[str] = None,
    ):
        self.index = index
        self.timestamp = timestamp
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.hash = block_hash or self.calculate_hash()

    def calculate_hash(self) -> str:
        """Calculates the SHA-256 hash of the block."""
        block_string = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
        }, sort_keys=True)
        return hashlib.sha256(block_string.encode()).hexdigest()

    @classmethod
    def from_db_model(cls, block_model) -> "Block":
        """Creates a Block instance from a SQLAlchemy model object."""
        return cls(
            index=block_model.id,
            timestamp=block_model.timestamp,
            transactions=block_model.transactions,
            previous_hash=block_model.previous_hash,
            nonce=block_model.nonce,
            block_hash=block_model.hash
        )

class Consensus:
    _instance: Optional["Consensus"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(Consensus, cls).__new__(cls)
        return cls._instance

    def __init__(self, app=None):
        if not hasattr(self, '_initialized'):
            if app is None:
                raise ValueError("Consensus must be initialized with a Flask app instance.")

            self.app = app
            self.nodes: Dict[str, Dict] = {}
            self.leader_id: Optional[str] = None

            with self.app.app_context():
                self._load_nodes_from_db()
                self._create_genesis_block_if_needed()
                self.elect_leader()

            self._initialized = True
            logger.info("Consensus system initialized and synchronized with database.")

    def _load_nodes_from_db(self):
        """Loads the list of registered nodes from the database."""
        nodes_from_db = ConsensusNode.query.all()
        self.nodes = {node.id: {"address": node.address} for node in nodes_from_db}
        logger.info(f"Loaded {len(self.nodes)} nodes from database.")

    def _create_genesis_block_if_needed(self):
        """Checks if the chain is empty and creates the genesis block if so."""
        first_block = ChainBlock.query.order_by(ChainBlock.id.asc()).first()
        if first_block is None:
            genesis_block = Block(
                index=0,
                timestamp=time.time(),
                transactions=[],
                previous_hash="0",
                nonce=0
            )
            new_block_model = ChainBlock(
                id=genesis_block.index,
                timestamp=genesis_block.timestamp,
                transactions=genesis_block.transactions,
                previous_hash=genesis_block.previous_hash,
                nonce=genesis_block.nonce,
                hash=genesis_block.hash
            )
            db.session.add(new_block_model)
            db.session.commit()
            logger.info("Genesis block created and saved to database.")

    def add_block(self, transactions: List[Dict]) -> Optional[Block]:
        """Creates a new block, validates it, and saves it to the database."""
        with self.app.app_context():
            try:
                last_block_model = ChainBlock.query.order_by(ChainBlock.id.desc()).first()
                if not last_block_model:
                    logger.error("No last block found. Genesis block may be missing.")
                    return None

                last_block = Block.from_db_model(last_block_model)
                new_index = last_block.index + 1
                new_timestamp = time.time()
                new_block = Block(
                    index=new_index,
                    timestamp=new_timestamp,
                    transactions=transactions,
                    previous_hash=last_block.hash,
                    nonce=0
                )

                # Simple Proof-of-Work placeholder: find nonce such that hash starts with '0000'
                target_prefix = "0000"
                while not new_block.hash.startswith(target_prefix):
                    new_block.nonce += 1
                    new_block.hash = new_block.calculate_hash()

                if not self.is_valid_new_block(new_block, last_block):
                    logger.error(f"New block validation failed at index {new_block.index}.")
                    return None

                new_block_model = ChainBlock(
                    id=new_block.index,
                    timestamp=new_block.timestamp,
                    transactions=new_block.transactions,
                    previous_hash=new_block.previous_hash,
                    nonce=new_block.nonce,
                    hash=new_block.hash
                )
                db.session.add(new_block_model)
                db.session.commit()

                logger.info(f"Block {new_block.index} added to blockchain with hash {new_block.hash}.")
                return new_block

            except Exception as e:
                logger.error(f"Failed to add block: {e}", exc_info=True)
                db.session.rollback()
                return None

    def is_valid_new_block(self, new_block: Block, previous_block: Block) -> bool:
        """Validates a new block against the previous block."""
        if previous_block.index + 1 != new_block.index:
            logger.warning("Invalid index for new block.")
            return False
        if previous_block.hash != new_block.previous_hash:
            logger.warning("Previous hash does not match for new block.")
            return False
        if new_block.calculate_hash() != new_block.hash:
            logger.warning("Hash calculation mismatch for new block.")
            return False
        return True

    def elect_leader(self) -> Optional[str]:
        """Elects a leader from the current list of registered nodes."""
        if not self.nodes:
            self.leader_id = None
            logger.info("No nodes registered, no leader elected.")
            return None
        self.leader_id = sorted(self.nodes.keys())[0]
        logger.info(f"Leader elected: {self.leader_id}")
        return self.leader_id

    def register_node(self, node_id: str, node_info: Dict) -> Dict:
        """Registers a new node and saves it to the database."""
        with self.app.app_context():
            try:
                existing_node = ConsensusNode.query.filter_by(id=node_id).first()
                if existing_node:
                    logger.info(f"Node {node_id} already registered.")
                    return {"status": "exists", "node_id": node_id}

                new_node = ConsensusNode(
                    id=node_id,
                    address=node_info.get("address", "")
                )
                db.session.add(new_node)
                db.session.commit()
                self.nodes[node_id] = {"address": new_node.address}
                logger.info(f"Node {node_id} registered successfully.")
                return {"status": "registered", "node_id": node_id}
            except Exception as e:
                logger.error(f"Failed to register node {node_id}: {e}", exc_info=True)
                db.session.rollback()
                return {"status": "error", "error": str(e)}

    def get_consensus_status(self) -> Dict:
        """Returns the current status of the consensus system."""
        return {
            "leader": self.leader_id,
            "nodes": list(self.nodes.keys()),
        }

# --- Singleton Accessor ---
_consensus_instance: Optional[Consensus] = None
_consensus_lock = threading.Lock()

def get_consensus_instance(app=None) -> Consensus:
    """
    Initializes and/or returns the singleton instance of the Consensus class.
    The Flask app instance must be provided on the first call.
    """
    global _consensus_instance
    if _consensus_instance is None:
        with _consensus_lock:
            if _consensus_instance is None:
                if app is None:
                    raise RuntimeError("Consensus must be initialized with the Flask app instance.")
                _consensus_instance = Consensus(app=app)
    return _consensus_instance

