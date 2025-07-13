import json
import hashlib
import time
import logging
from typing import List, Dict, Optional

from flask import Flask

# ==================================================================
# THIS IS THE CORRECTED IMPORT SECTION
# Using a single dot '.' because this file is at the same level as the 'db' package.
# ==================================================================
from .db.db_utils import get_session_scope
from .db.models import ChainBlock, ConsensusNode
# ==================================================================

logger = logging.getLogger(__name__)


class Block:
    """A data structure representing a single block in the blockchain."""
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
    def from_db_model(cls, block_model: ChainBlock) -> "Block":
        """Creates a Block instance from a SQLAlchemy ChainBlock model."""
        return cls(
            index=block_model.id,
            timestamp=block_model.timestamp,
            transactions=block_model.transactions,
            previous_hash=block_model.previous_hash,
            nonce=block_model.nonce,
            block_hash=block_model.hash
        )


class Consensus:
    """Manages the blockchain, node registration, and consensus logic."""
    def __init__(self):
        self.app: Optional[Flask] = None
        self.db = None
        self.nodes: Dict[str, Dict] = {}
        self.leader_id: Optional[str] = None
        self._initialized = False

    def init_app(self, app: Flask, db):
        """Initializes the Consensus system with the Flask app and database."""
        if self._initialized:
            return
            
        self.app = app
        self.db = db
        
        app.config.setdefault("POW_DIFFICULTY", "0000")
        self._initialized = True
        logger.info("Consensus system configured.")

    def _create_genesis_block_if_needed(self):
        """Checks if the chain is empty and creates the genesis block if so."""
        with get_session_scope() as session:
            if session.query(ChainBlock).first() is None:
                genesis_block = Block(index=0, timestamp=time.time(), transactions=[], previous_hash="0")
                new_block_model = ChainBlock(
                    id=genesis_block.index,
                    timestamp=genesis_block.timestamp,
                    transactions=genesis_block.transactions,
                    previous_hash=genesis_block.previous_hash,
                    nonce=genesis_block.nonce,
                    hash=genesis_block.hash
                )
                session.add(new_block_model)
                logger.info("Genesis block created and saved to database.")

    def elect_leader(self) -> Optional[str]:
        """Elects a leader from the current list of registered nodes."""
        with self.app.app_context():
            with get_session_scope() as session:
                nodes_from_db = session.query(ConsensusNode).all()
                self.nodes = {node.id: {"address": node.address} for node in nodes_from_db}

        if not self.nodes:
            self.leader_id = None
            return None
        self.leader_id = sorted(self.nodes.keys())[0]
        logger.info(f"Leader elected: {self.leader_id}")
        return self.leader_id

