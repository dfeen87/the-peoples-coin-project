import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set
import uuid
import requests
from requests.adapters import HTTPAdapter, Retry

from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import ChainBlock, LedgerEntry, UserAccount
from peoples_coin.validate.validate_transaction import validate_transaction

logger = logging.getLogger(__name__)

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def merkle_root_hash(transactions: List[Dict[str, Any]]) -> str:
    """Compute a Merkle root hash for a list of transaction dicts."""
    if not transactions:
        return sha256(b'')  # Empty root hash

    # Compute initial hashes of each transaction (as sorted JSON)
    txn_hashes = [sha256(json.dumps(tx, sort_keys=True).encode()) for tx in transactions]

    # Iteratively reduce by hashing pairs
    while len(txn_hashes) > 1:
        if len(txn_hashes) % 2 != 0:
            txn_hashes.append(txn_hashes[-1])  # Duplicate last hash if odd number
        txn_hashes = [
            sha256((txn_hashes[i] + txn_hashes[i+1]).encode())
            for i in range(0, len(txn_hashes), 2)
        ]
    return txn_hashes[0]


class Consensus:
    """
    Blockchain consensus without Proof-of-Work.
    Features:
    - Persistent DB chain (ChainBlock)
    - Block creation with Merkle root of transactions
    - Conflict resolution by longest valid chain
    - Node registration & communication with retries
    """

    def __init__(self):
        self.current_transactions: List[Dict[str, Any]] = []
        self.nodes: Set[str] = set()
        self.app = None
        self.db = None

        # Setup requests session with retries for robust node communication
        self.http_session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        self.http_session.mount("http://", HTTPAdapter(max_retries=retries))
        self.http_session.mount("https://", HTTPAdapter(max_retries=retries))

        logger.info("✅ Consensus instance created (No PoW).")

    def init_app(self, app: Optional[Any], db_instance: Optional[Any]) -> None:
        if self.app:
            logger.debug("Consensus already initialized, skipping.")
            return
        self.app = app
        self.db = db_instance
        logger.info("🚀 Consensus initialized.")

    def create_genesis_block_if_needed(self) -> None:
        with get_session_scope(self.db) as session:
            if session.query(ChainBlock).filter_by(block_number=0).first() is None:
                logger.info("🔷 No blocks found. Creating genesis block...")
                genesis_block = self.new_block(previous_hash='1', block_number=0)
                session.add(genesis_block)
                session.flush()
                logger.info(f"✅ Genesis block created: {genesis_block.hash}")
            else:
                logger.info("✅ Genesis block already exists.")

    def new_block(self, previous_hash: Optional[str] = None, block_number: Optional[int] = None) -> ChainBlock:
        with get_session_scope(self.db) as session:
            if block_number is None:
                last_block_obj = self.last_block()
                current_block_number = (last_block_obj.block_number + 1) if last_block_obj else 0
            else:
                current_block_number = block_number

            current_timestamp = datetime.now(timezone.utc)

            # Compute Merkle root of current transactions for block integrity
            merkle_root = merkle_root_hash(self.current_transactions)

            block_data = {
                'block_number': current_block_number,
                'timestamp': current_timestamp.isoformat(),
                'transactions_count': len(self.current_transactions),
                'previous_hash': previous_hash or (self.get_last_block_hash() if current_block_number > 0 else '1'),
                'merkle_root': merkle_root,
            }

            block_hash = self.hash(block_data)

            block = ChainBlock(
                block_number=block_data['block_number'],
                timestamp=current_timestamp,
                previous_hash=block_data['previous_hash'],
                hash=block_hash,
                merkle_root=merkle_root,
            )
            session.add(block)
            session.flush()

            logger.info(f"📦 New ChainBlock created (block_number={block.block_number}, hash={block.hash}).")

            if self.current_transactions:
                logger.info(f"📝 Processing {len(self.current_transactions)} transactions for Block {block.block_number}...")

                for tx_data in self.current_transactions:
                    validation_result = validate_transaction(tx_data)
                    if not validation_result.is_valid:
                        logger.error(f"🚫 Invalid transaction skipped in block creation: {validation_result.errors}")
                        continue

                    validated_tx_data = validation_result.data

                    # Resolve user IDs from Firebase UID to internal UUIDs
                    initiator_uuid = self._resolve_user_uuid(session, validated_tx_data.get('user_id'))

                    ledger_entry = LedgerEntry(
                        blockchain_tx_hash=sha256(json.dumps(validated_tx_data, sort_keys=True).encode()),
                        transaction_type=validated_tx_data.get('action_type', 'UNKNOWN'),
                        amount=validated_tx_data.get('loves_value', 0),
                        token_symbol='GOODWILL',
                        sender_address=validated_tx_data.get('sender_address', 'SYSTEM_MINTER'),
                        receiver_address=validated_tx_data.get('receiver_address', 'UNKNOWN_RECEIVER'),
                        block_number=block.block_number,
                        block_timestamp=block.timestamp,
                        status='CONFIRMED',
                        metadata=validated_tx_data.get('contextual_data', {}),
                        initiator_user_id=initiator_uuid,
                        receiver_user_id=validated_tx_data.get('receiver_user_id'), # if passed
                        goodwill_action_id=validated_tx_data.get('goodwill_action_id'),
                    )
                    session.add(ledger_entry)
                    logger.debug(f"  --> LedgerEntry created for tx hash: {ledger_entry.blockchain_tx_hash}")

                session.flush()
                logger.info(f"✅ {len(self.current_transactions)} LedgerEntry records persisted for Block {block.block_number}.")

            self.current_transactions.clear()
            return block

    @staticmethod
    def hash(block: Dict[str, Any]) -> str:
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def get_last_block_hash(self) -> Optional[str]:
        last = self.last_block()
        return last.hash if last else None

    def last_block(self) -> Optional[ChainBlock]:
        with get_session_scope(self.db) as session:
            return session.query(ChainBlock).order_by(ChainBlock.block_number.desc()).first()

    def register_node(self, address: str) -> None:
        self.nodes.add(address)
        logger.info(f"🌐 Node registered: {address}")

    def valid_chain(self, chain: List[Dict[str, Any]]) -> bool:
        if not chain:
            logger.warning("❌ Empty chain received for validation.")
            return False

        for i, block in enumerate(chain):
            if 'hash' not in block or 'previous_hash' not in block or 'merkle_root' not in block:
                logger.warning(f"❌ Block {i} missing required fields.")
                return False

            # Verify previous hash linkage
            if i > 0:
                prev_block = chain[i-1]
                expected_prev_hash = self.hash({
                    'block_number': prev_block['block_number'],
                    'timestamp': prev_block['timestamp'],
                    'transactions_count': len(prev_block.get('transactions', [])),
                    'previous_hash': prev_block['previous_hash'],
                    'merkle_root': prev_block.get('merkle_root', ''),
                })
                if block['previous_hash'] != expected_prev_hash:
                    logger.warning(f"❌ Invalid previous hash at block {i}. Expected {expected_prev_hash[:8]}, got {block['previous_hash'][:8]}")
                    return False

            # Recompute block hash and verify matches stored hash
            block_data = {
                'block_number': block['block_number'],
                'timestamp': block['timestamp'],
                'transactions_count': len(block.get('transactions', [])),
                'previous_hash': block['previous_hash'],
                'merkle_root': block['merkle_root'],
            }
            recalculated_hash = self.hash(block_data)
            if block['hash'] != recalculated_hash:
                logger.warning(f"❌ Invalid block hash at block {i}. Expected {recalculated_hash[:8]}, got {block['hash'][:8]}")
                return False

            # Timestamp sanity: not from future (+ 5 min tolerance)
            block_time = datetime.fromisoformat(block['timestamp'])
            if block_time > datetime.now(timezone.utc) + timedelta(minutes=5):
                logger.warning(f"❌ Block {i} timestamp is from the future.")
                return False

        logger.info("✅ Chain validated successfully.")
        return True

    def resolve_conflicts(self) -> bool:
        logger.info("🔄 Resolving conflicts…")
        new_chain = None
        max_length = self.get_chain_length()

        for node_address in self.nodes:
            try:
                url = f"https://{node_address}/chain"
                response = self.http_session.get(url, timeout=5)
                response.raise_for_status()
                data = response.json()
                chain_data = data.get('chain')
                if not isinstance(chain_data, list):
                    logger.warning(f"Chain from {node_address} is not a list. Skipping.")
                    continue

                chain_length = len(chain_data)
                if chain_length > max_length and self.valid_chain(chain_data):
                    max_length = chain_length
                    new_chain = chain_data
                    logger.info(f"🔄 Found longer valid chain from {node_address} (length: {chain_length})")

            except requests.exceptions.RequestException as e:
                logger.warning(f"Failed to fetch chain from {node_address}: {e}")
            except Exception as e:
                logger.exception(f"Unexpected error processing chain from {node_address}: {e}")

        if new_chain:
            self.replace_chain(new_chain)
            logger.info("✅ Local chain replaced with network chain.")
            return True

        logger.info("ℹ️ Local chain remains authoritative.")
        return False

    def get_chain_length(self) -> int:
        with get_session_scope(self.db) as session:
            return session.query(ChainBlock).count()

    def replace_chain(self, chain_data: List[Dict[str, Any]]) -> None:
        with get_session_scope(self.db) as session:
            try:
                session.query(LedgerEntry).delete()
                session.query(ChainBlock).delete()
                logger.info("📝 Cleared local chain and ledger for replacement.")

                for block_dict in chain_data:
                    block = ChainBlock(
                        block_number=block_dict['block_number'],
                        timestamp=datetime.fromisoformat(block_dict['timestamp']),
                        previous_hash=block_dict['previous_hash'],
                        hash=block_dict['hash'],
                        merkle_root=block_dict.get('merkle_root', ''),
                    )
                    session.add(block)
                    session.flush()

                    for tx_data in block_dict.get('transactions', []):
                        validation_result = validate_transaction(tx_data)
                        if not validation_result.is_valid:
                            logger.error(f"🚫 Invalid transaction in replaced chain block {block.block_number}: {validation_result.errors}")
                            continue

                        validated_tx_data = validation_result.data
                        initiator_uuid = self._resolve_user_uuid(session, validated_tx_data.get('user_id'))

                        ledger_entry = LedgerEntry(
                            blockchain_tx_hash=sha256(json.dumps(validated_tx_data, sort_keys=True).encode()),
                            goodwill_action_id=validated_tx_data.get('goodwill_action_id'),
                            transaction_type=validated_tx_data.get('action_type', 'UNKNOWN'),
                            amount=validated_tx_data.get('loves_value', 0),
                            token_symbol='GOODWILL',
                            sender_address=validated_tx_data.get('sender_address', 'SYSTEM_MINTER'),
                            receiver_address=validated_tx_data.get('receiver_address', 'UNKNOWN_RECEIVER'),
                            block_number=block.block_number,
                            block_timestamp=block.timestamp,
                            status='CONFIRMED',
                            metadata=validated_tx_data.get('contextual_data', {}),
                            initiator_user_id=initiator_uuid,
                            receiver_user_id=validated_tx_data.get('receiver_user_id'),
                        )
                        session.add(ledger_entry)
                        logger.debug(f"  --> LedgerEntry re-added (tx_hash: {ledger_entry.blockchain_tx_hash})")

                logger.info("✅ Local chain and ledger updated successfully.")

            except Exception as e:
                logger.exception("💥 Failed to replace chain and ledger atomically.")
                raise

    def add_transaction(self, transaction: Dict[str, Any]) -> int:
        self.current_transactions.append(transaction)
        logger.info(f"➕ Transaction added (total queued: {len(self.current_transactions)}).")

        with get_session_scope(self.db) as session:
            last_block_number = session.query(ChainBlock.block_number).order_by(ChainBlock.block_number.desc()).scalar()
            return (last_block_number + 1) if last_block_number is not None else 0

    def _resolve_user_uuid(self, session, firebase_uid: Optional[str]) -> Optional[uuid.UUID]:
        """Resolve Firebase UID to internal UserAccount UUID or return None."""
        if not firebase_uid:
            return None
        user = session.query(UserAccount).filter_by(firebase_uid=firebase_uid).first()
        return user.id if user else None

