import hashlib
import json
import time
import logging
from typing import List, Dict, Any, Optional, Set

import requests
from multiprocessing import Pool, cpu_count

from peoples_coin.db.db_utils import get_session_scope
from peoples_coin.db.models import ChainBlock

logger = logging.getLogger(__name__)


class Consensus:
    """
    Production-grade blockchain consensus mechanism:
    - Persistent chain in DB
    - Proof of Work (parallelizable)
    - Conflict resolution using total work
    - Supports genesis block, validation, node registration
    """

    def __init__(self):
        self.current_transactions: List[Dict[str, Any]] = []
        self.nodes: Set[str] = set()
        self.difficulty: str = "0000"
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
        with get_session_scope(self.db) as session:
            if session.query(ChainBlock).count() == 0:
                logger.info("🔷 No blocks found. Creating genesis block...")
                genesis_block = self.new_block(proof=100, previous_hash='1')
                session.add(genesis_block)
                session.flush()
                logger.info(f"✅ Genesis block created: {genesis_block.hash}")
            else:
                logger.info("✅ Genesis block already exists.")

    def new_block(self, proof: int, previous_hash: Optional[str] = None) -> ChainBlock:
        block_data = {
            'timestamp': time.time(),
            'transactions': self.current_transactions.copy(),
            'proof': proof,
            'previous_hash': previous_hash or self.get_last_block_hash() or '1',
        }

        block_hash = self.hash(block_data)

        block = ChainBlock(
            timestamp=block_data['timestamp'],
            transactions=block_data['transactions'],
            previous_hash=block_data['previous_hash'],
            nonce=proof,
            hash=block_hash,
        )

        self.current_transactions.clear()
        logger.info(f"📦 New block created: {block.hash}")
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
            return session.query(ChainBlock).order_by(ChainBlock.id.desc()).first()

    def proof_of_work(self, last_proof: int) -> int:
        logger.info("⛏️ Starting proof of work…")
        proof = 0

        # Single-threaded fallback
        while not self.valid_proof(last_proof, proof):
            proof += 1

        logger.info(f"💡 Proof of work found: {proof}")
        return proof

    def parallel_proof_of_work(self, last_proof: int) -> int:
        logger.info("⚡ Parallelizing proof of work…")
        with Pool(cpu_count()) as pool:
            for proof in pool.imap_unordered(self._check_proof, ((last_proof, i) for i in range(1, 1_000_000_000))):
                if proof is not None:
                    logger.info(f"💡 Parallel PoW found: {proof}")
                    pool.terminate()
                    return proof

    def _check_proof(self, args):
        last_proof, proof = args
        if self.valid_proof(last_proof, proof):
            return proof
        return None

    def valid_proof(self, last_proof: int, proof: int) -> bool:
        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash.startswith(self.difficulty)

    def register_node(self, address: str) -> None:
        self.nodes.add(address)
        logger.info(f"🌐 Node registered: {address}")

    def valid_chain(self, chain: List[Dict[str, Any]]) -> bool:
        if not chain:
            logger.warning("❌ Empty chain received for validation.")
            return False

        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]

            if block['previous_hash'] != self.hash(last_block):
                logger.warning(f"❌ Invalid previous hash at block {current_index}")
                return False

            if not self.valid_proof(last_block['proof'], block['proof']):
                logger.warning(f"❌ Invalid PoW at block {current_index}")
                return False

            last_block = block
            current_index += 1

        logger.info("✅ Chain validated successfully.")
        return True

    def resolve_conflicts(self) -> bool:
        """
        Resolve conflicts by replacing with the chain with highest total work.
        """
        logger.info("🔄 Resolving conflicts…")
        new_chain = None
        max_work = self.total_work()

        for node in self.nodes:
            try:
                response = requests.get(f"http://{node}/api/chain", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    chain = data.get('chain')

                    if not self.valid_chain(chain):
                        logger.warning(f"Chain from {node} is invalid.")
                        continue

                    work = self.calculate_work(chain)

                    if work > max_work:
                        max_work = work
                        new_chain = chain
                        logger.info(f"🔄 Found better chain from {node} (work: {work})")

            except Exception as e:
                logger.warning(f"Failed to fetch chain from {node}: {e}")

        if new_chain:
            self.replace_chain(new_chain)
            logger.info("✅ Local chain replaced with better chain.")
            return True

        logger.info("ℹ️ Local chain remains authoritative.")
        return False

    def replace_chain(self, chain: List[Dict[str, Any]]) -> None:
        with get_session_scope(self.db) as session:
            session.query(ChainBlock).delete()
            for index, block_data in enumerate(chain):
                block = ChainBlock(
                    id=index + 1,
                    timestamp=block_data['timestamp'],
                    transactions=block_data['transactions'],
                    previous_hash=block_data['previous_hash'],
                    nonce=block_data['proof'],
                    hash=block_data['hash'],
                )
                session.add(block)
            logger.info("📝 Local chain updated with new chain.")

    def total_work(self) -> int:
        """
        Calculate the total work of the current chain.
        """
        with get_session_scope(self.db) as session:
            chain = session.query(ChainBlock).order_by(ChainBlock.id).all()
            return self.calculate_work([{
                'timestamp': blk.timestamp,
                'transactions': blk.transactions,
                'previous_hash': blk.previous_hash,
                'proof': blk.nonce,
                'hash': blk.hash
            } for blk in chain])

    def calculate_work(self, chain: List[Dict[str, Any]]) -> int:
        """
        Total work is simply the sum of (2^difficulty_bits) per block.
        """
        bits = len(self.difficulty)
        return len(chain) * (2 ** bits)

