import json
import hashlib
import time
import logging
from typing import List, Dict, Optional

from flask import Flask

# Assuming these utilities and models exist from previous files
from ..db.db_utils import get_session_scope
from ..db.models import ChainBlock, ConsensusNode

logger = logging.getLogger(__name__)


class Block:
    """
    A data structure representing a single block in the blockchain.
    This is used for in-memory calculations before database persistence.
    """
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
        # Calculate the hash upon creation if not provided.
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
    """
    Manages the blockchain, node registration, and consensus logic.
    Designed to be initialized as a Flask extension.
    """
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

        # The app context is required for database operations.
        with self.app.app_context():
            self._load_nodes_from_db()
            self._create_genesis_block_if_needed()
            self.elect_leader()

        self._initialized = True
        logger.info("Consensus system initialized and synchronized with database.")

    def _load_nodes_from_db(self):
        """Loads the list of registered nodes from the database."""
        with get_session_scope() as session:
            nodes_from_db = session.query(ConsensusNode).all()
            self.nodes = {node.id: {"address": node.address} for node in nodes_from_db}
        logger.info(f"Loaded {len(self.nodes)} nodes from database.")

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

    def mine_new_block(self, transactions: List[Dict]) -> Block:
        """
        Creates a new block and solves the Proof-of-Work puzzle.

        Returns:
            The new, mined Block object, ready to be added to the chain.
        """
        with self.app.app_context():
            last_block_model = self.db.session.query(ChainBlock).order_by(ChainBlock.id.desc()).first()
            last_block = Block.from_db_model(last_block_model)
            
            new_block = Block(
                index=last_block.index + 1,
                timestamp=time.time(),
                transactions=transactions,
                previous_hash=last_block.hash
            )

            target_prefix = self.app.config["POW_DIFFICULTY"]
            while not new_block.hash.startswith(target_prefix):
                new_block.nonce += 1
                new_block.hash = new_block.calculate_hash()
            
            logger.info(f"Mined new block {new_block.index} with nonce {new_block.nonce}.")
            return new_block

    def add_block(self, new_block: Block) -> bool:
        """Validates a new block and saves it to the database."""
        with get_session_scope() as session:
            last_block_model = session.query(ChainBlock).order_by(ChainBlock.id.desc()).first()
            last_block = Block.from_db_model(last_block_model)

            if not self.is_valid_new_block(new_block, last_block):
                logger.error(f"Attempted to add invalid block at index {new_block.index}.")
                return False

            new_block_model = ChainBlock(
                id=new_block.index,
                timestamp=new_block.timestamp,
                transactions=new_block.transactions,
                previous_hash=new_block.previous_hash,
                nonce=new_block.nonce,
                hash=new_block.hash
            )
            session.add(new_block_model)
            logger.info(f"Block {new_block.index} added to the blockchain.")
            return True

    def is_valid_new_block(self, new_block: Block, previous_block: Block) -> bool:
        """Validates a new block against the previous block."""
        if previous_block.index + 1 != new_block.index:
            logger.warning(f"Validation failed: Invalid index. Expected {previous_block.index + 1}, got {new_block.index}.")
            return False
        if previous_block.hash != new_block.previous_hash:
            logger.warning("Validation failed: Previous hash does not match.")
            return False
        if new_block.calculate_hash() != new_block.hash:
            logger.warning("Validation failed: Hash calculation mismatch.")
            return False
        return True

    def is_chain_valid(self, chain: List[ChainBlock]) -> bool:
        """Determines if a given blockchain is valid by checking the entire chain."""
        if not chain:
            return False
        
        last_block = Block.from_db_model(chain[0])
        # Skip the genesis block and iterate from the second block
        for block_model in chain[1:]:
            current_block = Block.from_db_model(block_model)
            if not self.is_valid_new_block(current_block, last_block):
                return False
            last_block = current_block
        return True

    def elect_leader(self) -> Optional[str]:
        """Elects a leader from the current list of registered nodes (simple version)."""
        if not self.nodes:
            self.leader_id = None
            logger.info("No nodes registered, no leader elected.")
            return None
        # A simple, deterministic election: sort by ID and pick the first.
        self.leader_id = sorted(self.nodes.keys())[0]
        logger.info(f"Leader elected: {self.leader_id}")
        return self.leader_id

    def register_node(self, node_id: str, address: str) -> Dict:
        """Registers a new node and saves it to the database."""
        with get_session_scope() as session:
            if session.query(ConsensusNode).filter_by(id=node_id).first():
                return {"status": "exists", "node_id": node_id}
            
            new_node = ConsensusNode(id=node_id, address=address)
            session.add(new_node)
            self.nodes[node_id] = {"address": address}
            logger.info(f"Node {node_id} registered successfully.")
            return {"status": "registered", "node_id": node_id}

    def get_consensus_status(self) -> Dict:
        """Returns the current status of the consensus system."""
        return {
            "leader": self.leader_id,
            "nodes": list(self.nodes.keys()),
        }

    def reset_nodes_and_elect_leader(self):
        """
        Deletes all nodes from the database and in-memory, then re-elects a leader.
        This is a destructive action for testing or administrative use.
        """
        with get_session_scope() as session:
            num_deleted = session.query(ConsensusNode).delete()
            logger.info(f"Deleted {num_deleted} nodes from the database.")
        
        # Reset in-memory state and re-elect leader (which will be None)
        self.nodes.clear()
        self.elect_leader()

