import json
import os
import threading
import time
import logging
from typing import List, Dict, Optional

CHAIN_FILE = "chain.json"
LOCK = threading.RLock()
GENESIS_TIMESTAMP = 1688582400  # Fixed timestamp for genesis block

# Configure basic logging only if not already configured (optional, but good practice)
# You might want to remove this line if Flask handles all logging for the app.
# logging.basicConfig(level=logging.INFO) # Keep or remove based on overall app logging strategy
logger = logging.getLogger(__name__)


class Block:
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
        import hashlib

        block_string = json.dumps(
            {
                "index": self.index,
                "timestamp": self.timestamp,
                "transactions": self.transactions,
                "previous_hash": self.previous_hash,
                "nonce": self.nonce,
            },
            sort_keys=True,
        )
        return hashlib.sha256(block_string.encode()).hexdigest()

    def to_dict(self) -> Dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
        }

    @staticmethod
    def from_dict(data: Dict) -> "Block":
        return Block(
            index=data["index"],
            timestamp=data["timestamp"],
            transactions=data["transactions"],
            previous_hash=data["previous_hash"],
            nonce=data.get("nonce", 0),
            block_hash=data["hash"],
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

    def __init__(self):
        # This part ensures __init__ only runs once for the singleton
        if not hasattr(self, '_initialized'):
            self.chain: List[Block] = []
            self.nodes: Dict[str, Dict] = {}  # node_id -> node_info
            self.leader_id: Optional[str] = None
            self.load_chain()
            self.elect_leader()
            self._initialized = True


    def load_chain(self) -> None:
        # NOTE: CHAIN_FILE is relative to the current working directory
        # For a Flask app, it's generally better to place data files
        # in a fixed location like an 'instance' folder.
        # e.g., CHAIN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'instance', 'chain.json')
        # or pass the app.instance_path to Consensus on init.
        # For now, we'll keep it as is, but be aware of the implications.
        
        # Consider making CHAIN_FILE dynamic if needed, e.g., if app.instance_path is passed
        # For now, let's assume it attempts to open in the CWD of the flask command.

        with LOCK:
            if os.path.exists(CHAIN_FILE):
                try:
                    with open(CHAIN_FILE, "r") as f:
                        data = json.load(f)
                        self.chain = [Block.from_dict(b) for b in data]
                    if not self.is_chain_valid():
                        logger.warning("Loaded chain is invalid, creating genesis block.")
                        self._create_genesis_block()
                except (json.JSONDecodeError, IOError) as e:
                    logger.error(f"Error loading chain file: {e}. Creating genesis block.")
                    self._create_genesis_block()
            else:
                logger.info("Chain file not found, creating genesis block.")
                self._create_genesis_block()

    def _create_genesis_block(self) -> None:
        genesis_block = Block(
            index=0,
            timestamp=GENESIS_TIMESTAMP,
            transactions=[],
            previous_hash="0",
        )
        self.chain = [genesis_block]
        self.save_chain()
        logger.info("Genesis block created.")

    def save_chain(self) -> None:
        with LOCK:
            try:
                with open(CHAIN_FILE, "w") as f:
                    json.dump([block.to_dict() for block in self.chain], f, indent=4)
                logger.debug("Chain saved successfully.")
            except IOError as e:
                logger.error(f"Error saving chain file: {e}")

    def add_block(self, transactions: List[Dict]) -> Block:
        with LOCK:
            last_block = self.chain[-1]
            new_block = Block(
                index=last_block.index + 1,
                timestamp=time.time(),
                transactions=transactions,
                previous_hash=last_block.hash,
            )
            # Optional: add proof-of-work or other validation here
            if self.is_valid_new_block(new_block, last_block):
                self.chain.append(new_block)
                self.save_chain()
                logger.info(f"Block {new_block.index} added to chain.")
                return new_block
            else:
                logger.error("Attempted to add invalid block.")
                raise ValueError("Invalid block")

    def is_valid_new_block(self, new_block: Block, previous_block: Block) -> bool:
        if previous_block.index + 1 != new_block.index:
            logger.debug("Invalid index")
            return False
        if previous_block.hash != new_block.previous_hash:
            logger.debug("Invalid previous hash")
            return False
        if new_block.calculate_hash() != new_block.hash:
            logger.debug("Invalid hash calculation")
            return False
        # Additional checks (e.g. proof-of-work) can be added here
        return True

    def is_chain_valid(self) -> bool:
        """Validate the entire chain integrity."""
        with LOCK:
            for i in range(1, len(self.chain)):
                if not self.is_valid_new_block(self.chain[i], self.chain[i - 1]):
                    logger.error(f"Chain invalid at block {i}")
                    return False
            return True

    def elect_leader(self) -> Optional[str]:
        with LOCK:
            if not self.nodes:
                self.leader_id = None
                logger.info("No nodes available to elect leader.") # THIS IS THE LOG YOU ARE SEEING
                return None
            # Simple deterministic leader election based on lex order
            self.leader_id = sorted(self.nodes.keys())[0]
            logger.info(f"Leader elected: {self.leader_id}")
            return self.leader_id

    def register_node(self, node_id: str, node_info: Dict) -> Dict:
        with LOCK:
            if node_id in self.nodes:
                logger.warning(f"Node ID {node_id} already registered.")
                return {"error": "Node ID already registered"}
            if any(n.get("address") == node_info.get("address") for n in self.nodes.values()):
                logger.warning(f"Node address {node_info.get('address')} already registered.")
                return {"error": "Node address already registered"}

            self.nodes[node_id] = node_info
            self.elect_leader()
            logger.info(f"Node {node_id} registered successfully.")
            return {"message": "Node registered successfully", "total_nodes": len(self.nodes)}

    def reset_nodes(self) -> None:
        with LOCK:
            self.nodes.clear()
            self.leader_id = None
            logger.info("All nodes reset.")

    def get_consensus_status(self) -> Dict:
        with LOCK:
            status = {
                "chain_length": len(self.chain),
                "leader": self.leader_id,
                "nodes": list(self.nodes.keys()),
                "latest_block_hash": self.chain[-1].hash if self.chain else None,
            }
            logger.debug(f"Consensus status: {status}")
            return status

# Create a function to get the singleton instance of Consensus
# This avoids instantiating it at module load time.
_consensus_instance: Optional[Consensus] = None
_consensus_lock = threading.Lock()

def get_consensus_instance() -> Consensus:
    global _consensus_instance
    with _consensus_lock:
        if _consensus_instance is None:
            _consensus_instance = Consensus()
    return _consensus_instance


def get_consensus_status() -> Dict:
    return get_consensus_instance().get_consensus_status()


def add_block(transactions: List[Dict]) -> Block:
    return get_consensus_instance().add_block(transactions)


def register_node(node_id: str, node_info: Dict) -> Dict:
    return get_consensus_instance().register_node(node_id, node_info)


def reset_nodes() -> None:
    get_consensus_instance().reset_nodes()
