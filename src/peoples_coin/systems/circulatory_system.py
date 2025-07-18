import logging
from datetime import datetime, timezone
from sqlalchemy.orm.exc import NoResultFound
from decimal import Decimal
from typing import Tuple, Optional
import uuid

from flask import Flask

from peoples_coin.db.db_utils import get_session_scope
from peoples_coin.db.models import GoodwillAction, UserAccount, LedgerEntry, ChainBlock
from peoples_coin.consensus import Consensus # Import your Consensus class

logger = logging.getLogger(__name__)


class CirculatorySystem:
    """
    Handles the core logic of token minting based on completed goodwill actions,
    directly interacting with the custom blockchain.
    """

    def __init__(self):
        self.app: Optional[Flask] = None
        self.db = None
        self.consensus: Optional[Consensus] = None # Will hold the Consensus instance
        self._initialized = False
        logger.info("🫀 CirculatorySystem instance created.")

    def init_app(self, app: Flask, db, consensus_instance: Consensus): # Accept Consensus instance
        if self._initialized:
            return

        self.app = app
        self.db = db
        self.consensus = consensus_instance # Assign the Consensus instance

        self._initialized = True
        logger.info("🫀 CirculatorySystem initialized and configured with Consensus system.")

    def process_goodwill_for_minting(self, goodwill_action_id: uuid.UUID) -> Tuple[bool, str]:
        """
        Processes a verified GoodwillAction:
        1. Records it as a transaction in the custom blockchain.
        2. Records the internal blockchain transaction hash.
        3. Updates user's off-chain balance.
        4. Creates a LedgerEntry.
        This method is intended to be called by an asynchronous worker.
        """
        if not self._initialized or not self.consensus:
            msg = "🛑 CirculatorySystem or Consensus has not been properly initialized."
            logger.error(msg)
            return False, msg

        with get_session_scope(self.db) as session:
            try:
                goodwill_action = session.query(GoodwillAction).filter_by(id=goodwill_action_id).one()

                # Idempotency: Ensure action is verified and not yet issued on-chain
                if goodwill_action.status == 'ISSUED_ON_CHAIN':
                    msg = f"⏩ Mint skipped: GoodwillAction ID {goodwill_action_id} already issued on-chain ({goodwill_action.blockchain_tx_hash})."
                    logger.warning(msg)
                    return False, msg
                if goodwill_action.status != 'VERIFIED': # Assuming 'VERIFIED' is status after human/AI verification
                    msg = f"⏩ Mint skipped: GoodwillAction ID {goodwill_action_id} status='{goodwill_action.status}'. Must be 'VERIFIED'."
                    logger.warning(msg)
                    return False, msg

                performer_user_id_uuid = goodwill_action.performer_user_id
                loves_to_mint = Decimal(goodwill_action.loves_value)

                # Prepare transaction data for your custom blockchain
                # This should be a dict that your consensus system expects for a transaction
                transaction_data = {
                    "action_id": str(goodwill_action.id), # Link to your GoodwillAction
                    "performer_user_id": str(performer_user_id_uuid),
                    "action_type": goodwill_action.action_type,
                    "description": goodwill_action.description,
                    "loves_value": loves_to_mint,
                    "timestamp": datetime.now(timezone.utc).isoformat(), # Use current UTC time for transaction
                    # Add sender/receiver addresses if applicable for internal chain transactions
                    "sender_address": "system_mint_address", # Or resolved from a system wallet
                    "receiver_address": "user_wallet_address", # This would need to be resolved from UserWallet
                }
                
                # Step 1: Add transaction to the Consensus system
                # The add_transaction method in Consensus will store it in current_transactions
                # and return the index of the block it's targeting.
                index_of_next_block = self.consensus.add_transaction(transaction_data) 
                logger.info(f"⛓️ Transaction for GoodwillAction ID {goodwill_action_id} added to Consensus.")

                # Step 2: (Optional/Async) Trigger mining or await block inclusion
                # In a real setup, this would usually be an async call to a miner or
                # a background process would periodically mine blocks.
                # For simplicity here, we can simulate getting a hash (which would usually come after mining)
                
                # Simulate getting blockchain tx hash from the custom chain (e.g., hash of transaction itself or block hash)
                # In your custom chain, a transaction might get a unique ID/hash when included in a block
                custom_blockchain_tx_hash = f"CUSTOM_TX_{uuid.uuid4().hex}" # This would be from your chain's logic

                # Step 3: Update GoodwillAction status and internal blockchain_tx_hash
                goodwill_action.mark_issued_on_chain(tx_hash=custom_blockchain_tx_hash)
                session.add(goodwill_action)

                # Step 4: Create LedgerEntry record for this custom blockchain event
                # This would reflect the "mint" event on your custom chain
                ledger_entry = LedgerEntry(
                    blockchain_tx_hash=custom_blockchain_tx_hash,
                    goodwill_action_id=goodwill_action.id,
                    transaction_type='MINT_GOODWILL',
                    amount=loves_to_mint,
                    token_symbol='LOVES',
                    sender_address="system_minter_address", # Placeholder for your custom chain's minter
                    receiver_address=transaction_data["receiver_address"], # Use the resolved receiver
                    block_number=index_of_next_block, # Use the block index where it's included
                    block_timestamp=datetime.now(timezone.utc), # Use block timestamp from your chain
                    status='CONFIRMED', # Or PENDING, depending on your chain's confirmation
                    metadata=goodwill_action.contextual_data,
                    initiator_user_id=performer_user_id_uuid,
                    receiver_user_id=performer_user_id_uuid,
                )
                session.add(ledger_entry)

                # Step 5: Update UserAccount balance (off-chain cache)
                user_account = session.query(UserAccount).filter_by(id=performer_user_id_uuid).with_for_update().one()
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
