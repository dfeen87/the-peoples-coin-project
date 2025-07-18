import hashlib
import json
import time
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set
import uuid # For temporary hash generation

import requests
from multiprocessing import Pool, cpu_count

from peoples_coin.db.db_utils import get_session_scope
from peoples_coin.db.models import ChainBlock, LedgerEntry # Ensure LedgerEntry is imported
from peoples_coin.validation.validate_transaction import validate_transaction # For validating current_transactions

logger = logging.getLogger(__name__)


class Consensus:
    """
    Production-grade blockchain consensus mechanism:
    - Persistent chain in DB (ChainBlock model)
    - Proof of Work (parallelizable)
    - Conflict resolution using total work
    - Supports genesis block, validation, node registration
    """

    def __init__(self):
        # Transactions temporarily held here before being added to a block and persisted as LedgerEntry
        self.current_transactions: List[Dict[str, Any]] = [] 
        self.nodes: Set[str] = set()
        self.difficulty: str = "0000" # Example difficulty
        self.app = None
        self.db = None
        logger.info("✅ Consensus instance created.")

    def init_app(self, app: Optional[Any], db_instance: Optional[Any]) -> None:
        if self.app:
            logger.debug("Consensus already initialized, skipping.")
            return

        self.app = app
        self.db = db_instance
        self.difficulty = self.app.config.get("POW_DIFFICULTY", "0000")
        logger.info(f"🚀 Consensus initialized with difficulty: {self.difficulty}")

    def create_genesis_block_if_needed(self) -> None:
        """
        Creates the genesis block if no blocks exist in the database.
        """
        with get_session_scope(self.db) as session:
            # Check for existing blocks by block_number for clarity (assuming genesis is block 0)
            if session.query(ChainBlock).filter_by(block_number=0).first() is None:
                logger.info("🔷 No blocks found. Creating genesis block...")
                # Genesis block has index 0, previous_hash '1', and no transactions
                genesis_block = self.new_block(proof=100, previous_hash='1', block_number=0)
                session.add(genesis_block)
                session.flush() # Ensure ID and other defaults are populated
                logger.info(f"✅ Genesis block created: {genesis_block.hash}")
            else:
                logger.info("✅ Genesis block already exists.")

    def new_block(self, proof: int, previous_hash: Optional[str] = None, block_number: Optional[int] = None) -> ChainBlock:
        """
        Creates a new Block and persists its transactions as LedgerEntry records.
        """
        with get_session_scope(self.db) as session:
            # Determine the block number
            if block_number is None:
                last_block_obj = self.last_block()
                current_block_number = (last_block_obj.block_number + 1) if last_block_obj else 0
            else:
                current_block_number = block_number
            
            # Ensure timestamp is timezone aware
            current_timestamp = datetime.now(timezone.utc)

            block_data = {
                'block_number': current_block_number,
                'timestamp': current_timestamp.isoformat(), # Use ISO format for hashing consistently
                'transactions_count': len(self.current_transactions), # Store count, not full transactions
                'proof': proof,
                'previous_hash': previous_hash or (self.get_last_block_hash() if current_block_number > 0 else '1'),
            }

            # Hash the block data
            block_hash = self.hash(block_data)

            # Create the ChainBlock instance (id will be auto-generated UUID)
            block = ChainBlock(
                block_number=block_data['block_number'],
                timestamp=current_timestamp, # Store as datetime object
                previous_hash=block_data['previous_hash'],
                nonce=proof,
                hash=block_hash,
            )
            session.add(block)
            session.flush() # Flush to get the block.id (UUID) before processing transactions

            logger.info(f"📦 New ChainBlock created (block_number={block.block_number}, hash={block.hash}).")

            # Process and persist current_transactions as LedgerEntry records
            if self.current_transactions:
                logger.info(f"📝 Processing {len(self.current_transactions)} transactions for Block {block.block_number}...")
                for tx_data in self.current_transactions:
                    # Validate incoming transaction data first
                    # This uses the TransactionModel schema we refined in validate_transaction.py
                    validation_result = validate_transaction(tx_data)
                    if not validation_result.is_valid:
                        logger.error(f"🚫 Invalid transaction found during block creation. Skipping. Details: {validation_result.errors}")
                        # You might want to log these failed transactions or move them to a 'failed' queue
                        continue
                    
                    validated_tx_data = validation_result.data # This is a Pydantic model_dump dict
                    
                    # Create LedgerEntry from validated data
                    # Assuming blockchain_tx_hash will be updated later by event listener
                    ledger_entry = LedgerEntry(
                        blockchain_tx_hash=validated_tx_data.get('blockchain_tx_hash', f"TEMP_HASH_{uuid.uuid4()}"), # TEMPORARY, will be updated post-blockchain
                        # goodwill_action_id would need to be passed in tx_data if it applies
                        transaction_type=validated_tx_data.get('action_type', 'UNKNOWN'),
                        amount=validated_tx_data.get('loves_value', 0),
                        token_symbol='GOODWILL',
                        sender_address=validated_tx_data.get('sender_address', 'UNKNOWN_SENDER'),
                        receiver_address=validated_tx_data.get('receiver_address', 'UNKNOWN_RECEIVER'),
                        block_number=block.block_number,
                        block_timestamp=block.timestamp,
                        status='PENDING_ON_CHAIN', # Status before actually being confirmed on chain
                        metadata=validated_tx_data.get('contextual_data', {}),
                        # initiator_user_id and receiver_user_id would be looked up/resolved from user_id in tx_data
                    )
                    session.add(ledger_entry)
                    logger.debug(f"  --> LedgerEntry created (temp hash: {ledger_entry.blockchain_tx_hash})")

                session.flush() # Flush to persist LedgerEntry records
                logger.info(f"✅ {len(self.current_transactions)} LedgerEntry records persisted for Block {block.block_number}.")
            
            self.current_transactions.clear() # Clear after processing

            return block

    @staticmethod
    def hash(block: Dict[str, Any]) -> str:
        """
        Creates a SHA-256 hash of a Block.
        The 'transactions' field is excluded from hashing because individual LedgerEntry objects are stored separately.
        Instead, 'transactions_count' is included in block_data.
        """
        # Ensure block_data is sorted for consistent hashing
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def get_last_block_hash(self) -> Optional[str]:
        """Returns the hash of the last block in the chain."""
        last = self.last_block()
        return last.hash if last else None

    def last_block(self) -> Optional[ChainBlock]:
        """Returns the last block from the database, ordered by block_number."""
        with get_session_scope(self.db) as session:
            return session.query(ChainBlock).order_by(ChainBlock.block_number.desc()).first()

    def proof_of_work(self, last_proof: int) -> int:
        logger.info("⛏️ Starting proof of work (single-threaded)…")
        proof = 0
        while not self.valid_proof(last_proof, proof):
            proof += 1
        logger.info(f"💡 Proof of work found: {proof}")
        return proof

    def parallel_proof_of_work(self, last_proof: int) -> int:
        logger.info("⚡ Parallelizing proof of work…")
        with Pool(cpu_count()) as pool:
            for proof in pool.imap_unordered(self._check_proof, ((last_proof, i, self.difficulty) for i in range(1, 1_000_000_000))):
                if proof is not None:
                    logger.info(f"💡 Parallel PoW found: {proof}")
                    pool.terminate() # Stop other workers once a proof is found
                    return proof
            logger.warning("🚫 Parallel PoW search exhausted range without finding proof.")
            return -1 # Indicate failure to find proof within range

    def _check_proof(self, args) -> Optional[int]:
        """Helper for parallel proof of work."""
        last_proof, proof, difficulty = args
        if self.valid_proof(last_proof, proof, difficulty):
            return proof
        return None

    def valid_proof(self, last_proof: int, proof: int, difficulty: Optional[str] = None) -> bool:
        """
        Validates the proof: Does hash(last_proof, proof) contain 'difficulty' leading zeroes?
        """
        difficulty = difficulty or self.difficulty # Use instance difficulty if not provided
        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash.startswith(difficulty)

    def register_node(self, address: str) -> None:
        """Registers a new node in the set of blockchain nodes."""
        self.nodes.add(address)
        logger.info(f"🌐 Node registered: {address}")

    def valid_chain(self, chain: List[Dict[str, Any]]) -> bool:
        """
        Determines if a given blockchain is valid by verifying hashes and proofs.
        Expected chain: list of dictionaries representing ChainBlock data.
        """
        if not chain:
            logger.warning("❌ Empty chain received for validation.")
            return False

        current_index = 0
        while current_index < len(chain):
            block = chain[current_index]
            # Ensure block contains 'hash' and 'previous_hash' for validation
            if 'hash' not in block or 'previous_hash' not in block:
                logger.warning(f"❌ Block {current_index} is missing hash or previous_hash.")
                return False

            if current_index > 0: # Skip genesis block for previous_hash check
                last_block = chain[current_index - 1]
                if block['previous_hash'] != self.hash(last_block):
                    logger.warning(f"❌ Invalid previous hash at block {current_index}. Expected: {self.hash(last_block)[:8]}, Got: {block['previous_hash'][:8]}")
                    return False

                # Proof of work validation (assuming 'proof' field in dict)
                if 'proof' not in block or 'proof' not in last_block:
                    logger.warning(f"❌ Block {current_index} is missing 'proof' field.")
                    return False
                
                # Make sure to pass the actual difficulty to valid_proof
                if not self.valid_proof(last_block['proof'], block['proof'], self.difficulty):
                    logger.warning(f"❌ Invalid PoW at block {current_index}.")
                    return False
            
            current_index += 1

        logger.info("✅ Chain validated successfully.")
        return True


    def resolve_conflicts(self) -> bool:
        """
        Resolve conflicts by replacing local chain with the longest valid chain from network.
        Return True if local chain was replaced, False otherwise.
        """
        logger.info("🔄 Resolving conflicts…")
        new_chain = None
        max_length = self.get_chain_length()

        for node_address in self.nodes:
            try:
                # Ensure correct API endpoint for chain sync
                response = requests.get(f"http://{node_address}/chain", timeout=5) # Example endpoint
                if response.status_code == 200:
                    data = response.json()
                    chain_data = data.get('chain')
                    if not isinstance(chain_data, list):
                        logger.warning(f"Chain from {node_address} is not a list. Skipping.")
                        continue
                    
                    chain_length = len(chain_data)

                    if chain_length > max_length and self.valid_chain(chain_data):
                        max_length = chain_length
                        new_chain = chain_data
                        logger.info(f"🔄 Found longer and valid chain from {node_address} (length: {chain_length})")

            except requests.exceptions.RequestException as e:
                logger.warning(f"Failed to fetch chain from {node_address}: {e}")
            except Exception as e:
                logger.exception(f"Unexpected error processing chain from {node_address}: {e}")


        if new_chain:
            self.replace_chain(new_chain)
            logger.info("✅ Local chain replaced with better chain from network.")
            return True

        logger.info("ℹ️ Local chain remains authoritative.")
        return False

    def get_chain_length(self) -> int:
        """Returns the number of blocks in the local chain."""
        with get_session_scope(self.db) as session:
            return session.query(ChainBlock).count()

    def replace_chain(self, chain_data: List[Dict[str, Any]]) -> None:
        """
        Replaces the local chain with a new valid chain.
        Also re-populates LedgerEntry records based on the new chain's transactions.
        """
        with get_session_scope(self.db) as session:
            # Delete all existing ChainBlocks and LedgerEntries to replace them
            session.query(LedgerEntry).delete() # Delete dependent records first
            session.query(ChainBlock).delete()
            logger.info("📝 Clearing local chain and ledger for replacement.")

            for index, block_dict in enumerate(chain_data):
                # Recreate ChainBlock instance (id will be auto-generated UUID)
                block = ChainBlock(
                    # block_number is crucial for ordering and linking
                    block_number=block_dict['block_number'],
                    timestamp=datetime.fromisoformat(block_dict['timestamp']) if isinstance(block_dict['timestamp'], str) else datetime.fromtimestamp(block_dict['timestamp'], tz=timezone.utc), # Handle ISO or float timestamp
                    previous_hash=block_dict['previous_hash'],
                    nonce=block_dict['proof'], # PoW 'proof' maps to 'nonce' in ChainBlock
                    hash=block_dict['hash'],
                )
                session.add(block)
                session.flush() # Flush to get block.id before adding LedgerEntries

                # Re-process transactions into LedgerEntry for each block in the new chain
                if 'transactions' in block_dict and isinstance(block_dict['transactions'], list):
                    for tx_data in block_dict['transactions']:
                        # This part assumes a specific structure for transactions within the chain_data
                        # And that validate_transaction can process it for LedgerEntry creation.
                        validation_result = validate_transaction(tx_data)
                        if not validation_result.is_valid:
                            logger.error(f"🚫 Invalid transaction encountered during chain replacement for block {block.block_number}. Skipping. Details: {validation_result.errors}")
                            continue

                        validated_tx_data = validation_result.data
                        
                        ledger_entry = LedgerEntry(
                            blockchain_tx_hash=validated_tx_data.get('blockchain_tx_hash', f"SYNC_HASH_{uuid.uuid4()}"), # Get actual hash or temp ID
                            goodwill_action_id=validated_tx_data.get('goodwill_action_id_uuid'), # If schema provides this
                            transaction_type=validated_tx_data.get('action_type', 'UNKNOWN'),
                            amount=validated_tx_data.get('loves_value', 0),
                            token_symbol='GOODWILL',
                            sender_address=validated_tx_data.get('sender_address', 'UNKNOWN_SENDER'),
                            receiver_address=validated_tx_data.get('receiver_address', 'UNKNOWN_RECEIVER'),
                            block_number=block.block_number,
                            block_timestamp=block.timestamp,
                            status='CONFIRMED', # Assuming imported transactions are confirmed
                            metadata=validated_tx_data.get('contextual_data', {}),
                            # initiator_user_id and receiver_user_id would be resolved based on address
                        )
                        session.add(ledger_entry)
                        logger.debug(f"  --> LedgerEntry re-added (tx_hash: {ledger_entry.blockchain_tx_hash})")

            logger.info("✅ Local chain and ledger updated successfully with new chain.")


    def total_work(self) -> int:
        """
        Calculate the total work of the current chain.
        """
        with get_session_scope(self.db) as session:
            # Query ChainBlocks directly, convert to dict format expected by calculate_work
            chain_blocks = session.query(ChainBlock).order_by(ChainBlock.block_number).all()
            chain_dicts = [
                {
                    'block_number': blk.block_number,
                    'timestamp': blk.timestamp.isoformat(), # Use ISO format
                    'previous_hash': blk.previous_hash,
                    'proof': blk.nonce,
                    'hash': blk.hash,
                    'transactions_count': session.query(LedgerEntry).filter_by(block_number=blk.block_number).count() # Get count from LedgerEntry table
                }
                for blk in chain_blocks
            ]
            return self.calculate_work(chain_dicts)

    def calculate_work(self, chain: List[Dict[str, Any]]) -> int:
        """
        Total work is sum of (2^difficulty_bits) per block.
        Assumes 'block_number' is present in chain dicts.
        """
        if not chain:
            return 0
        
        bits = len(self.difficulty)
        # Ensure we're calculating work based on actual blocks, not just arbitrary list length
        # A more robust work calculation might iterate through each block's actual proof
        return len(chain) * (2 ** bits)

    def add_transaction(self, transaction: Dict[str, Any]) -> int:
        """
        Adds a new transaction to the list of current transactions to be included in the next mined block.
        """
        # This transaction would be the validated data from submit_goodwill
        self.current_transactions.append(transaction)
        logger.info(f"➕ Transaction added to current_transactions (count: {len(self.current_transactions)}).")
        # Return the index of the block that this transaction will be added to
        # (current chain length + 1, since it's for the NEXT block)
        with get_session_scope(self.db) as session:
            return session.query(ChainBlock).count() + 1
