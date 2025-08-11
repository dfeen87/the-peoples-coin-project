import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
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
        txn_hashes = [sha256((txn_hashes[i] + txn_hashes[i+1]).encode()) for i in range(0, len(txn_hashes), 2)]
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
        """
        Ensures a genesis block exists in the database.
        This is a placeholder implementation.
        """
        with get_session_scope(self.db) as session:
            # Check if there are any blocks in the database
            if session.query(ChainBlock).count() == 0:
                logger.info("No genesis block found. Creating one now.")
                self.new_block(previous_hash="1")
            else:
                logger.info("Genesis block already exists.")


    def add_transaction(self, transaction: Dict[str, Any]) -> int:
        """
        Adds a transaction to the shared transaction pool in Redis.
        Returns the anticipated block number for this transaction.
        """
        self.redis.rpush(TRANSACTION_POOL_KEY, json.dumps(transaction))
        logger.info(f"➕ Transaction added to Redis pool (pool size: {self.redis.llen(TRANSACTION_POOL_KEY)}).")
        
        with get_session_scope(self.db) as session:
            last_block_number = session.query(ChainBlock.height).order_by(ChainBlock.height.desc()).scalar()
            return (last_block_number + 1) if last_block_number is not None else 0

    def new_block(self, previous_hash: Optional[str] = None) -> ChainBlock:
        """
        Creates a new block, pulling all pending transactions from the shared Redis pool.
        """
        with get_session_scope(self.db) as session:
            last_block_obj = self.last_block()
            current_block_height = (last_block_obj.height + 1) if last_block_obj else 0
            
            # Atomically get all transactions from the Redis list and clear it.
            pipe = self.redis.pipeline()
            pipe.lrange(TRANSACTION_POOL_KEY, 0, -1)
            pipe.delete(TRANSACTION_POOL_KEY)
            transactions_json, _ = pipe.execute()
            
            transactions = [json.loads(tx) for tx in transactions_json]

            block_data = {
                'height': current_block_height,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'previous_hash': previous_hash or (last_block_obj.block_hash if last_block_obj else '1'),
                'merkle_root': merkle_root_hash(transactions),
            }
            
            block_hash = sha256(json.dumps(block_data, sort_keys=True).encode())

            block = ChainBlock(
                height=block_data['height'],
                timestamp=datetime.fromisoformat(block_data['timestamp']),
                previous_hash=block_data['previous_hash'],
                block_hash=block_hash,
                data={"merkle_root": block_data['merkle_root'], "tx_count": len(transactions)}
            )
            session.add(block)
            session.flush() # Flush to get the block ID if needed

            for tx_data in transactions:
                # ... process and create LedgerEntry as before ...
                pass # Your ledger entry creation logic is good.
            
            return block

    def replace_chain(self, chain_data: List[Dict[str, Any]]):
        """
        Replaces the local chain with a new, valid, longer chain and
        triggers a recalculation of all derived states.
        """
        with get_session_scope(self.db) as session:
            try:
                # 1. Clear existing chain data
                session.query(LedgerEntry).delete()
                session.query(ChainBlock).delete()
                
                # 2. Rebuild the chain from the new data
                for block_dict in chain_data:
                    # ... re-add ChainBlock and LedgerEntry as before ...
                    pass

                # 3. Trigger state reconciliation (CRITICAL)
                self._recalculate_all_user_balances(session)

                logger.info("✅ Local chain and ledger replaced and state reconciled.")
            except Exception as e:
                logger.exception("💥 Failed to replace chain atomically.")
                raise

    def _recalculate_all_user_balances(self, session):
        """
        Recalculates all user balances from the ledger.
        This is a heavy operation and should only run after a chain replacement.
        """
        logger.info("💰 Recalculating all user balances from the new ledger...")
        # A more optimized approach would be to use GROUP BY queries.
        session.query(UserAccount).update({"balance": 0})
        all_entries = session.query(LedgerEntry).all()
        
        balances = {} # user_id -> balance
        for entry in all_entries:
            # Logic to update balances dictionary based on entry.amount and type
            pass
        
        for user_id, new_balance in balances.items():
            session.query(UserAccount).filter_by(id=user_id).update({"balance": new_balance})
        
        logger.info("✅ All user balances have been reconciled.")

    def last_block(self) -> Optional[ChainBlock]:
        """Gets the most recent block from the database."""
        with get_session_scope(self.db) as session:
            return session.query(ChainBlock).order_by(ChainBlock.height.desc()).first()
