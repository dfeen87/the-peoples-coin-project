import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set
import uuid # For temporary hash generation if needed

import requests # Keep requests for node communication/conflict resolution

from peoples_coin.db.db_utils import get_session_scope
from peoples_coin.db.models import ChainBlock, LedgerEntry # Ensure LedgerEntry is imported
from peoples_coin.validation.validate_transaction import validate_transaction # For validating current_transactions

logger = logging.getLogger(__name__)


class Consensus:
    """
    Core blockchain consensus mechanism for your custom chain (no Proof of Work).
    - Persistent chain in DB (ChainBlock model)
    - Block creation based on accumulated transactions
    - Conflict resolution using longest chain (no PoW work calculation)
    - Supports genesis block, validation, node registration
    """

    def __init__(self):
        self.current_transactions: List[Dict[str, Any]] = [] # Transactions temporarily held
        self.nodes: Set[str] = set()
        # self.difficulty: str = "0000" # REMOVED: Difficulty is for PoW, no longer needed for mining
        self.app = None
        self.db = None
        logger.info("✅ Consensus instance created (No PoW).")

    def init_app(self, app: Optional[Any], db_instance: Optional[Any]) -> None:
        if self.app:
            logger.debug("Consensus already initialized, skipping.")
            return

        self.app = app
        self.db = db_instance
        # self.difficulty = self.app.config.get("POW_DIFFICULTY", "0000") # REMOVED: PoW difficulty
        logger.info("🚀 Consensus initialized.")

    def create_genesis_block_if_needed(self) -> None:
        """
        Creates the genesis block (Block 0) if no blocks exist in the database.
        """
        with get_session_scope(self.db) as session:
            if session.query(ChainBlock).filter_by(block_number=0).first() is None:
                logger.info("🔷 No blocks found. Creating genesis block...")
                # Genesis block has block_number 0, previous_hash '1', and no transactions
                # No 'proof' (nonce) for non-PoW chain
                genesis_block = self.new_block(previous_hash='1', block_number=0)
                session.add(genesis_block)
                session.flush() # Ensure ID and other defaults are populated
                logger.info(f"✅ Genesis block created: {genesis_block.hash}")
            else:
                logger.info("✅ Genesis block already exists.")

    def new_block(self, previous_hash: Optional[str] = None, block_number: Optional[int] = None) -> ChainBlock:
        """
        Creates a new Block, including current_transactions as LedgerEntry records.
        This block creation does NOT involve Proof-of-Work (mining).
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
                # 'proof': proof, # REMOVED: No proof (nonce) for non-PoW
                'previous_hash': previous_hash or (self.get_last_block_hash() if current_block_number > 0 else '1'),
            }

            # Hash the block data
            block_hash = self.hash(block_data)

            # Create the ChainBlock instance (id will be auto-generated UUID)
            block = ChainBlock(
                block_number=block_data['block_number'],
                timestamp=current_timestamp, # Store as datetime object
                previous_hash=block_data['previous_hash'],
                # nonce=proof, # REMOVED: No nonce for non-PoW
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
                    validation_result = validate_transaction(tx_data)
                    if not validation_result.is_valid:
                        logger.error(f"🚫 Invalid transaction found during block creation. Skipping. Details: {validation_result.errors}")
                        continue
                    
                    validated_tx_data = validation_result.data
                    
                    # Create LedgerEntry from validated data
                    # blockchain_tx_hash is now the unique ID of the transaction within your custom chain
                    ledger_entry = LedgerEntry(
                        blockchain_tx_hash=f"CHAIN_TX_{uuid.uuid4().hex}", # Use a derived hash or unique ID for your custom chain
                        transaction_type=validated_tx_data.get('action_type', 'UNKNOWN'),
                        amount=validated_tx_data.get('loves_value', 0),
                        token_symbol='GOODWILL',
                        sender_address=validated_tx_data.get('sender_address', 'SYSTEM_MINTER'), # Default to SYSTEM_MINTER
                        receiver_address=validated_tx_data.get('receiver_address', 'UNKNOWN_RECEIVER'),
                        block_number=block.block_number,
                        block_timestamp=block.timestamp,
                        status='CONFIRMED', # Immediately confirmed if included in a block
                        metadata=validated_tx_data.get('contextual_data', {}),
                        # initiator_user_id and receiver_user_id would be looked up/resolved from user_id in tx_data
                    )
                    # Link to GoodwillAction if available in tx_data
                    if 'goodwill_action_id' in validated_tx_data:
                        ledger_entry.goodwill_action_id = validated_tx_data['goodwill_action_id']

                    # Resolve user_ids from performer_user_id (Firebase UID from schema)
                    # This implies you would pass these as part of the transaction_data
                    if 'performer_user_id' in validated_tx_data:
                        # You'd need to query UserAccount by Firebase UID to get internal UUID
                        pass # Placeholder for user_id resolution logic

                    session.add(ledger_entry)
                    logger.debug(f"  --> LedgerEntry created for custom chain (hash: {ledger_entry.blockchain_tx_hash})")

                session.flush() # Flush to persist LedgerEntry records
                logger.info(f"✅ {len(self.current_transactions)} LedgerEntry records persisted for Block {block.block_number}.")
            
            self.current_transactions.clear() # Clear after processing

            return block

    @staticmethod
    def hash(block: Dict[str, Any]) -> str:
        """
        Creates a SHA-256 hash of a Block.
        Transactions are excluded from hashing; 'transactions_count' is included instead.
        """
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

    def register_node(self, address: str) -> None:
        """Registers a new node in the set of blockchain nodes."""
        self.nodes.add(address)
        logger.info(f"🌐 Node registered: {address}")

    def valid_chain(self, chain: List[Dict[str, Any]]) -> bool:
        """
        Determines if a given blockchain is valid by verifying hashes (no PoW check).
        Expected chain: list of dictionaries representing ChainBlock data.
        """
        if not chain:
            logger.warning("❌ Empty chain received for validation.")
            return False

        current_index = 0
        while current_index < len(chain):
            block = chain[current_index]
            if 'hash' not in block or 'previous_hash' not in block:
                logger.warning(f"❌ Block {current_index} is missing hash or previous_hash.")
                return False

            if current_index > 0: # Skip genesis block for previous_hash check
                last_block = chain[current_index - 1]
                if block['previous_hash'] != self.hash(last_block):
                    logger.warning(f"❌ Invalid previous hash at block {current_index}. Expected: {self.hash(last_block)[:8]}, Got: {block['previous_hash'][:8]}")
                    return False

                # REMOVED: No Proof of Work validation here for non-PoW chain
                # if 'proof' not in block or 'proof' not in last_block:
                #     logger.warning(f"❌ Block {current_index} is missing 'proof' field.")
                #     return False
                # if not self.valid_proof(last_block['proof'], block['proof'], self.difficulty):
                #     logger.warning(f"❌ Invalid PoW at block {current_index}.")
                #     return False
            
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
        max_length = self.get_chain_length() # Longest chain is now the "most work"

        for node_address in self.nodes:
            try:
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

        logger.info("ℹ️ Local chain remains authoritative (no better chain found).")
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

            for block_dict in chain_data: # Iterate through the block dictionaries
                # Recreate ChainBlock instance (id will be auto-generated UUID)
                block = ChainBlock(
                    block_number=block_dict['block_number'],
                    timestamp=datetime.fromisoformat(block_dict['timestamp']) if isinstance(block_dict['timestamp'], str) else datetime.fromtimestamp(block_dict['timestamp'], tz=timezone.utc),
                    previous_hash=block_dict['previous_hash'],
                    # nonce=block_dict['proof'], # REMOVED: No nonce
                    hash=block_dict['hash'],
                )
                session.add(block)
                session.flush() # Flush to get block.id before adding LedgerEntries

                # Re-process transactions into LedgerEntry for each block in the new chain
                if 'transactions' in block_dict and isinstance(block_dict['transactions'], list):
                    for tx_data in block_dict['transactions']:
                        validation_result = validate_transaction(tx_data)
                        if not validation_result.is_valid:
                            logger.error(f"🚫 Invalid transaction encountered during chain replacement for block {block.block_number}. Skipping. Details: {validation_result.errors}")
                            continue

                        validated_tx_data = validation_result.data
                        
                        # Populate LedgerEntry based on validated_tx_data
                        ledger_entry = LedgerEntry(
                            blockchain_tx_hash=validated_tx_data.get('blockchain_tx_hash', f"SYNC_HASH_{uuid.uuid4()}"),
                            goodwill_action_id=validated_tx_data.get('goodwill_action_id'), # Assuming goodwill_action_id is now a direct field in tx_data
                            transaction_type=validated_tx_data.get('action_type', 'UNKNOWN'),
                            amount=validated_tx_data.get('loves_value', 0),
                            token_symbol='GOODWILL',
                            sender_address=validated_tx_data.get('sender_address', 'SYSTEM_MINTER'),
                            receiver_address=validated_tx_data.get('receiver_address', 'UNKNOWN_RECEIVER'),
                            block_number=block.block_number,
                            block_timestamp=block.timestamp,
                            status='CONFIRMED',
                            metadata=validated_tx_data.get('contextual_data', {}),
                            initiator_user_id=validated_tx_data.get('initiator_user_id'), # Assuming these are passed
                            receiver_user_id=validated_tx_data.get('receiver_user_id'), # Assuming these are passed
                        )
                        session.add(ledger_entry)
                        logger.debug(f"  --> LedgerEntry re-added (tx_hash: {ledger_entry.blockchain_tx_hash})")

            logger.info("✅ Local chain and ledger updated successfully with new chain.")


    # REMOVED: Proof of Work related methods
    # def proof_of_work(self, last_proof: int) -> int: ...
    # def parallel_proof_of_work(self, last_proof: int) -> int: ...
    # def _check_proof(self, args) -> Optional[int]: ...
    # def valid_proof(self, last_proof: int, proof: int, difficulty: Optional[str] = None) -> bool: ...

    def add_transaction(self, transaction: Dict[str, Any]) -> int:
        """
        Adds a new transaction to the list of current transactions to be included in the next block.
        Returns the block_number of the block this transaction will be added to.
        """
        # This transaction would be the validated data from submit_goodwill
        self.current_transactions.append(transaction)
        logger.info(f"➕ Transaction added to current_transactions (count: {len(self.current_transactions)}).")
        
        # Return the block number of the *next* block to be mined/created
        with get_session_scope(self.db) as session:
            last_block_number = session.query(ChainBlock.block_number).order_by(ChainBlock.block_number.desc()).scalar()
            return (last_block_number + 1) if last_block_number is not None else 0
