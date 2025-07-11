"""
consensus.py
Implements the core consensus and blockchain logic for The People's Coin.
This version is designed to be backed by a database for robust state management.
"""

import json
import os
import threading
import time
import logging
from typing import List, Dict, Optional
import hashlib

# Import the main db object and the new models you would create
# from ..db import db
# from ..db.models import ChainBlock, ConsensusNode

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
        # from ..db.models import ConsensusNode
        # nodes_from_db = ConsensusNode.query.all()
        # self.nodes = {node.id: {"address": node.address} for node in nodes_from_db}
        # logger.info(f"Loaded {len(self.nodes)} nodes from database.")
        pass # Placeholder for DB logic

    def _create_genesis_block_if_needed(self):
        """Checks if the chain is empty and creates the genesis block if so."""
        # from ..db.models import ChainBlock, db
        # if ChainBlock.query.first() is None:
        #     genesis_block = Block(index=0, timestamp=time.time(), transactions=[], previous_hash="0")
        #     new_block_model = ChainBlock(...)
        #     db.session.add(new_block_model)
        #     db.session.commit()
        #     logger.info("Genesis block created in database.")
        pass # Placeholder for DB logic

    def add_block(self, transactions: List[Dict]) -> Block:
        """Creates a new block, validates it, and saves it to the database."""
        # from ..db.models import ChainBlock, db
        with self.app.app_context():
            # FIXED: Indented the pass statement
            pass # Placeholder for DB logic

    def is_valid_new_block(self, new_block: Block, previous_block: Block) -> bool:
        """Validates a new block against the previous block."""
        if previous_block.index + 1 != new_block.index:
            return False
        if previous_block.hash != new_block.previous_hash:
            return False
        if new_block.calculate_hash() != new_block.hash:
            return False
        return True

    def elect_leader(self) -> Optional[str]:
        """Elects a leader from the current list of registered nodes."""
        if not self.nodes:
            self.leader_id = None
            return None
        self.leader_id = sorted(self.nodes.keys())[0]
        logger.info(f"Leader elected: {self.leader_id}")
        return self.leader_id

    def register_node(self, node_id: str, node_info: Dict) -> Dict:
        """Registers a new node and saves it to the database."""
        # from ..db.models import ConsensusNode, db
        # address = node_info.get("address")
        with self.app.app_context():
            # FIXED: Indented the pass statement
            pass # Placeholder for DB logic

    def get_consensus_status(self) -> Dict:
        """Returns the current status of the consensus system from the database."""
        # from ..db.models import ChainBlock
        with self.app.app_context():
            # FIXED: Indented the pass statement
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
