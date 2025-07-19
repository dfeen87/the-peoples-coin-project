import logging
from datetime import datetime, timezone
from sqlalchemy.orm.exc import NoResultFound
from decimal import Decimal
from typing import Tuple, Optional
import uuid

from flask import Flask

from peoples_coin.db.db_utils import get_session_scope
from peoples_coin.db.models import GoodwillAction, UserAccount, LedgerEntry, ChainBlock, UserWallet
from peoples_coin.consensus import Consensus

logger = logging.getLogger(__name__)


class CirculatorySystem:
    """
    Handles the core logic of token minting based on completed goodwill actions,
    directly interacting with the custom blockchain.
    """

    def __init__(self):
        self.app: Optional[Flask] = None
        self.db = None
        self.consensus: Optional[Consensus] = None
        self.minter_wallet_address: Optional[str] = None
        self._initialized = False
        logger.info("🫀 CirculatorySystem instance created.")

    def init_app(self, app: Flask, db, consensus_instance: Consensus) -> None:
        """
        Initialize CirculatorySystem with Flask app, database, and Consensus instance.
        """
        if self._initialized:
            return

        self.app = app
        self.db = db
        self.consensus = consensus_instance
        self.minter_wallet_address = self.app.config.get("MINTER_WALLET_ADDRESS", "system_minter_address")
        self._initialized = True
        logger.info("🫀 CirculatorySystem initialized and configured with Consensus system.")

    def process_goodwill_for_minting(self, goodwill_action_id: uuid.UUID) -> Tuple[bool, str]:
        """
        Process a verified GoodwillAction for minting on the custom blockchain.
        Returns a tuple (success: bool, message: str).
        """
        if not self._initialized or not self.consensus:
            msg = "🛑 CirculatorySystem or Consensus has not been properly initialized."
            logger.error(msg)
            return False, msg

        now_utc = datetime.now(timezone.utc)

        with get_session_scope(self.db) as session:
            try:
                goodwill_action = session.query(GoodwillAction).with_for_update().filter_by(id=goodwill_action_id).one()

                # Idempotency: Only process if verified and not yet issued on chain
                if goodwill_action.status == 'ISSUED_ON_CHAIN':
                    msg = (
                        f"⏩ Mint skipped: GoodwillAction ID {goodwill_action_id} already issued on-chain "
                        f"({goodwill_action.blockchain_tx_hash})."
                    )
                    logger.warning(msg)
                    return False, msg

                if goodwill_action.status != 'VERIFIED':
                    msg = (
                        f"⏩ Mint skipped: GoodwillAction ID {goodwill_action_id} status='{goodwill_action.status}'. "
                        f"Must be 'VERIFIED'."
                    )
                    logger.warning(msg)
                    return False, msg

                performer_user_id_uuid = goodwill_action.performer_user_id
                loves_to_mint = Decimal(goodwill_action.loves_value)

                user_account = session.query(UserAccount).filter_by(id=performer_user_id_uuid).first()
                if not user_account:
                    msg = f"❌ Minting failed: UserAccount not found for performer ID {performer_user_id_uuid}."
                    logger.error(msg)
                    goodwill_action.status = 'FAILED_USER_NOT_FOUND'
                    return False, msg

                user_wallet = session.query(UserWallet).filter_by(user_id=user_account.id, is_primary=True).first()
                if not user_wallet:
                    msg = f"❌ Minting failed: No primary wallet found for user ID {user_account.id}."
                    logger.error(msg)
                    goodwill_action.status = 'FAILED_WALLET_MISSING'
                    return False, msg

                transaction_data = {
                    "action_id": str(goodwill_action.id),
                    "performer_user_id": str(performer_user_id_uuid),
                    "action_type": goodwill_action.action_type,
                    "description": goodwill_action.description,
                    "loves_value": float(loves_to_mint),
                    "timestamp": now_utc.isoformat(),
                    "sender_address": self.minter_wallet_address,
                    "receiver_address": user_wallet.public_address,
                    "metadata": goodwill_action.contextual_data,
                }

                index_of_next_block = self.consensus.add_transaction(transaction_data)
                logger.info(f"⛓️ Transaction for GoodwillAction ID {goodwill_action_id} added to Consensus.")

                # Placeholder for blockchain transaction hash; replace with real on-chain tx hash
                custom_blockchain_tx_hash = f"CUSTOM_TX_{uuid.uuid4().hex}"

                if not custom_blockchain_tx_hash:
                    msg = f"❌ Custom blockchain minting failed for GoodwillAction ID {goodwill_action_id}."
                    logger.error(msg)
                    goodwill_action.status = 'FAILED_ON_CHAIN_MINT'
                    return False, msg

                goodwill_action.mark_issued_on_chain(tx_hash=custom_blockchain_tx_hash)
                session.add(goodwill_action)

                ledger_entry = LedgerEntry(
                    blockchain_tx_hash=custom_blockchain_tx_hash,
                    goodwill_action_id=goodwill_action.id,
                    transaction_type='MINT_GOODWILL',
                    amount=loves_to_mint,
                    token_symbol='LOVES',
                    sender_address=self.minter_wallet_address,
                    receiver_address=user_wallet.public_address,
                    block_number=index_of_next_block,
                    block_timestamp=now_utc,
                    status='CONFIRMED',
                    metadata=goodwill_action.contextual_data,
                    initiator_user_id=performer_user_id_uuid,
                    receiver_user_id=performer_user_id_uuid,
                )
                session.add(ledger_entry)

                user_account.balance += loves_to_mint
                session.add(user_account)

                msg = (
                    f"✅ Successfully recorded {loves_to_mint:.4f} Loves for user {performer_user_id_uuid} in custom chain. "
                    f"Custom Chain Tx: {custom_blockchain_tx_hash}. New balance: {user_account.balance:.4f}."
                )
                logger.info(msg)
                return True, msg

            except NoResultFound:
                msg = f"❌ Minting failed: GoodwillAction ID {goodwill_action_id} not found."
                logger.error(msg)
                return False, msg

            except Exception as e:
                logger.error(
                    f"💥 Unexpected error processing mint for GoodwillAction ID {goodwill_action_id}: {e}",
                    exc_info=True
                )
                return False, "An internal error occurred during custom chain minting."

