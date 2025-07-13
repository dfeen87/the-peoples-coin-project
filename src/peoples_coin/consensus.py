import hashlib
import json
import time
import logging
from typing import List, Dict, Any, Optional

# Assuming these imports are available from your project structure
from .db.db_utils import get_session_scope, retry_db_operation
from .db.models import ChainBlock, DataEntry # Import DataEntry if needed for block content
# --- CRITICAL FIX: REMOVE direct import of 'db' from extensions here. ---
# from .extensions import db # REMOVED

logger = logging.getLogger(__name__)

class Consensus:
    """
    Manages the blockchain's consensus mechanism, including block creation,
    mining (Proof-of-Work), and chain validation.
    """
    def __init__(self):
        self.chain: List[Dict[str, Any]] = []
        self.current_transactions: List[Dict[str, Any]] = []
        self.nodes: set = set()
        self.difficulty: str = "0000" # Default difficulty, can be configured
        self.app = None # To store the Flask app instance
        self.db = None # Store the db instance here
        logger.info("Consensus system instance created.")

    def init_app(self, app: Optional[Any], db_instance: Optional[Any]): # db_instance is passed from __init__.py
        """
        Initializes the Consensus system with the Flask app and db instance.
        """
        if self.app is not None:
            return # Already initialized

        self.app = app
        # The db_instance is passed from the app factory, ensuring it's the correct one.
        self.db = db_instance # Store the db_instance for later use in methods
        self.difficulty = self.app.config.get("POW_DIFFICULTY", "0000")
        logger.info(f"Consensus system configured with difficulty: {self.difficulty}.")
        
        # --- CRITICAL FIX: REMOVE genesis block creation from init_app ---
        # It will now be called via a separate CLI command after migrations.
        # with self.app.app_context():
        #     self._create_genesis_block_if_needed()


    def _create_genesis_block_if_needed(self):
        """
        Creates the genesis block if the chain is empty in the database.
        This method is now intended to be called via a separate CLI command
        *after* Alembic migrations have run.
        """
        # --- CRITICAL FIX: Pass the self.db (the stored db_instance) to get_session_scope ---
        with get_session_scope(self.db) as session:
            if session.query(ChainBlock).count() == 0:
                logger.info("No blocks found in DB. Creating genesis block...")
                genesis_block = self.new_block(proof=100, previous_hash='1')
                session.add(genesis_block)
                session.flush() # Ensure ID is available if needed
                logger.info(f"Genesis block created and added to DB: {genesis_block.hash}")
            else:
                logger.info("Blockchain already exists in DB. Skipping genesis block creation.")

    def new_block(self, proof: int, previous_hash: Optional[str] = None) -> ChainBlock:
        """
        Creates a new Block and adds it to the chain.
        """
        block_data = {
            'timestamp': time.time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1]) if self.chain else '1',
        }
        block_hash = self.hash(block_data)
        block = ChainBlock(
            timestamp=block_data['timestamp'],
            transactions=block_data['transactions'],
            previous_hash=block_data['previous_hash'],
            nonce=proof, # Using proof as nonce for simplicity in this PoW example
            hash=block_hash
        )
        self.current_transactions = [] # Clear current transactions
        self.chain.append(block_data) # Add to in-memory chain (for current run)
        return block

    @staticmethod
    def hash(block: Dict[str, Any]) -> str:
        """
        Creates a SHA-256 hash of a Block.
        """
        # We must make sure that the Dictionary is Ordered, or we'll have inconsistent hashes
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def last_block(self) -> Optional[ChainBlock]:
        """
        Returns the last Block in the chain from the database.
        """
        # --- CRITICAL FIX: Pass the self.db (the stored db_instance) to get_session_scope ---
        with get_session_scope(self.db) as session:
            return session.query(ChainBlock).order_by(ChainBlock.id.desc()).first()

    def proof_of_work(self, last_proof: int) -> int:
        """
        Simple Proof of Work Algorithm:
         - Find a number p' such that hash(pp') contains leading zeroes equal to difficulty
         - p is the previous proof, and p' is the new proof
        """
        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof += 1
        return proof

    def valid_proof(self, last_proof: int, proof: int) -> bool:
        """
        Validates the proof: Does hash(last_proof, proof) contain leading zeroes equal to difficulty?
        """
        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:len(self.difficulty)] == self.difficulty

    def register_node(self, address: str):
        """
        Add a new node to the list of nodes.
        """
        self.nodes.add(address)

    def valid_chain(self, chain: List[Dict[str, Any]]) -> bool:
        """
        Determine if a given blockchain is valid.
        """
        last_block_data = chain[0]
        current_index = 1

        while current_index < len(chain):
            block_data = chain[current_index]
            logger.debug(f'{last_block_data}')
            logger.debug(f'{block_data}')

            # Check that the hash of the block is correct
            if block_data['previous_hash'] != self.hash(last_block_data):
                return False

            # Check that the Proof of Work is correct
            if not self.valid_proof(last_block_data['proof'], block_data['proof']):
                return False

            last_block_data = block_data
            current_index += 1

        return True

    def resolve_conflicts(self) -> bool:
        """
        This is our Consensus Algorithm, it resolves conflicts
        by replacing our chain with the longest one in the network.
        """
        neighbours = self.nodes
        new_chain = None

        # We're only looking for chains longer than ours
        max_length = len(self.chain)

        # Grab and verify the chains from all the nodes in our network
        for node in neighbours:
            # In a real scenario, this would involve network requests
            # For simplicity, we assume a mechanism to get other chains
            # response = requests.get(f'http://{node}/chain')
            # if response.status_code == 200:
            #     length = response.json()['length']
            #     chain = response.json()['chain']
            #     if length > max_length and self.valid_chain(chain):
            #         max_length = length
            #         new_chain = chain
            pass # Placeholder for actual network logic

        if new_chain:
            # --- CRITICAL FIX: Pass the self.db (the stored db_instance) to get_session_scope ---
            with get_session_scope(self.db) as session:
                # Replace our chain in the database
                session.query(ChainBlock).delete() # Clear existing chain
                for block_data in new_chain:
                    block = ChainBlock(
                        id=block_data['index'],
                        timestamp=block_data['timestamp'],
                        transactions=block_data['transactions'],
                        previous_hash=block_data['previous_hash'],
                        nonce=block_data['proof'],
                        hash=self.hash(block_data)
                    )
                    session.add(block)
                logger.info("Chain replaced with a longer valid chain.")
            return True

        logger.info("Our chain is authoritative.")
        return False


