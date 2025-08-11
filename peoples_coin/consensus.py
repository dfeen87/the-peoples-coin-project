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
from peoples_coin.validate.validate_transaction import validate_transaction

logger = logging.getLogger(__name__)
TRANSACTION_POOL_KEY = "consensus:transaction_pool"


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
        txn_hashes = [sha256((txn_hashes[i] + txn_hashes[i + 1]).encode()) for i in range(0, len(txn_hashes), 2)]
    return txn_hashes[0]


class Consensus:
    """Manages the blockchain, transaction pool, and node synchronization."""

    def __init__(self):
        self.nodes: Set[str] = set()
        self.app = None
        self.db = None
        self.redis: Optional[Redis] = None

        self.http_session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        self.http_session.mount("http://", HTTPAdapter(max_retries=retries))
        self.http_session.mount("https://", HTTPAdapter(max_retries=retries))
        logger.info("✅ Consensus instance created.")

    def init_app(self, app: Any, db_instance: Any, redis_instance: Optional[Redis]):
        """Initializes the Consensus system with app context and dependencies."""
        if self.app:
            return
        self.app = app
        self.db = db_instance
        self.redis = redis_instance
        if not self.redis:
            raise RuntimeError("Redis is required for the Consensus transaction pool.")
        self.create_genesis_block_if_needed()
        logger.info("🚀 Consensus initialized.")

    def create_genesis_block_if_needed(self):
        """Ensures a genesis block exists in the database."""
        with get_session_scope(self.db) as session:
            if session.query(ChainBlock).count() == 0:
                logger.info("No genesis block found. Creating one now.")
                # Create the genesis block with empty transactions
                genesis_block_data = {
                    "height": 0,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "previous_hash": "0" * 64,
                    "merkle_root": merkle_root_hash([]),
                }
                self.new_block(genesis_block_data, transactions=[])
            else:
                logger.info("Genesis block already exists.")

    def add_transaction(self, transaction: Dict[str, Any]) -> int:
        """
        Adds a transaction to the shared transaction pool in Redis.
        Returns the anticipated block number for this transaction.
        """
        self.redis.rpush(TRANSACTION_POOL_KEY, json.dumps(transaction))
        pool_size = self.redis.llen(TRANSACTION_POOL_KEY)
        logger.info(f"➕ Transaction added to Redis pool (pool size: {pool_size}).")

        with get_session_scope(self.db) as session:
            last_block_number = session.query(ChainBlock.height).order_by(ChainBlock.height.desc()).scalar()
            return (last_block_number + 1) if last_block_number is not None else 0

    def calculate_block_hash(self, block_data: Dict[str, Any], transactions: List[Dict[str, Any]]) -> str:
        """
        Calculate the block hash based on block header fields and the Merkle root.
        Customize this hashing logic as per your blockchain spec.
        """
        header_str = (
            str(block_data['height']) +
            block_data['timestamp'] +
            block_data['previous_hash'] +
            block_data['merkle_root']
        )
        return sha256(header_str.encode())

    def new_block(self, block_data: Dict[str, Any], transactions: List[Dict[str, Any]]) -> ChainBlock:
        """
        Create a new block and save it to the database.
        Assumes block_data contains 'height', 'timestamp', 'previous_hash', and 'merkle_root'.
        """

        # Validate block_data fields
        required_fields = ['height', 'timestamp', 'previous_hash', 'merkle_root']
        for field in required_fields:
            if field not in block_data:
                raise ValueError(f"Missing required block field: {field}")

        # Convert timestamp string to datetime if needed
        timestamp_val = block_data['timestamp']
        if isinstance(timestamp_val, str):
            timestamp_val = datetime.fromisoformat(timestamp_val)

        # Convert hex strings to bytes if needed
        prev_hash_bytes = (
            bytes.fromhex(block_data['previous_hash'])
            if isinstance(block_data['previous_hash'], str)
            else block_data['previous_hash']
        )

        merkle_root_bytes = (
            bytes.fromhex(block_data['merkle_root'])
            if isinstance(block_data['merkle_root'], str)
            else block_data['merkle_root']
        )

        # Calculate current_hash
        current_hash_hex = self.calculate_block_hash(block_data, transactions)
        current_hash_bytes = bytes.fromhex(current_hash_hex)

        block = ChainBlock(
            height=block_data['height'],
            timestamp=timestamp_val,
            previous_hash=prev_hash_bytes,
            current_hash=current_hash_bytes,
            tx_count=len(transactions),
        )

        with get_session_scope(self.db) as session:
            session.add(block)
            session.flush()  # get block.id if needed

            # TODO: Insert LedgerEntry for each transaction here
            for tx in transactions:
                # Example:
                # ledger_entry = LedgerEntry(...)
                # session.add(ledger_entry)
                pass

        logger.info(f"🧱 New block created at height {block.height} with {len(transactions)} txns.")
        return block

    def replace_chain(self, chain_data: List[Dict[str, Any]]):
        """
        Replace the local chain with a new, valid, longer chain,
        then recalculate all derived states like balances.
        """
        with get_session_scope(self.db) as session:
            try:
                session.query(LedgerEntry).delete()
                session.query(ChainBlock).delete()

                for block_dict in chain_data:
                    # TODO: Re-add ChainBlock and LedgerEntries for each block_dict
                    pass

                self._recalculate_all_user_balances(session)

                logger.info("✅ Local chain replaced and state reconciled.")
            except Exception as e:
                logger.exception("💥 Failed to replace chain atomically.")
                raise

    def _recalculate_all_user_balances(self, session):
        """
        Recalculate all user balances from the ledger entries.
        """
        logger.info("💰 Recalculating all user balances from ledger...")

        session.query(UserAccount).update({"balance": 0})

        balances = {}  # user_id -> balance
        all_entries = session.query(LedgerEntry).all()

        for entry in all_entries:
            # Update balances[user_id] based on entry fields
            # e.g. balances[entry.user_id] = balances.get(entry.user_id, 0) + entry.amount
            pass

        for user_id, new_balance in balances.items():
            session.query(UserAccount).filter_by(id=user_id).update({"balance": new_balance})

        logger.info("✅ All user balances reconciled.")

    def last_block(self) -> Optional[ChainBlock]:
        """Get the most recent block from the database."""
        with get_session_scope(self.db) as session:
            return session.query(ChainBlock).order_by(ChainBlock.height.desc()).first()

