import logging
from datetime import datetime, timezone
from sqlalchemy.orm.exc import NoResultFound
from decimal import Decimal
from typing import Tuple, Optional
import uuid

from flask import Flask

from peoples_coin.db.db_utils import get_session_scope
from peoples_coin.db.models import GoodwillAction, UserAccount, LedgerEntry, ChainBlock, UserWallet # Import UserWallet
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
        1. Records it as a transaction in the custom blockchain via Consensus.
        2. Records the internal blockchain transaction hash.
        3. Updates user's off-chain balance.
        4. Creates a LedgerEntry record.
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

                # Step 1: Resolve receiver_address (user's primary wallet)
                user_account = session.query(UserAccount).filter_by(id=performer_user_id_uuid).first()
                if not user_account:
                    msg = f"❌ Minting failed: UserAccount not found for performer ID {performer_user_id_uuid}."
                    logger.error(msg)
                    goodwill_action.status = 'FAILED_USER_NOT_FOUND' # New status
                    return False, msg

                user_wallet = session.query(UserWallet).filter_by(user_id=user_account.id, is_primary=True).first()
                if not user_wallet:
                    msg = f"❌ Minting failed: No primary wallet found for user ID {user_account.id}."
                    logger.error(msg)
                    goodwill_action.status = 'FAILED_WALLET_MISSING' # Update status
                    return False, msg
                receiver_address = user_wallet.public_address

                # Prepare transaction data for your custom blockchain (for Consensus.add_transaction)
                transaction_data = {
                    "action_id": str(goodwill_action.id), # Link to your GoodwillAction
                    "performer_user_id": str(performer_user_id_uuid),
                    "action_type": goodwill_action.action_type,
                    "description": goodwill_action.description,
                    "loves_value": float(loves_to_mint), # Convert Decimal to float for JSON/simplicity in consensus
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sender_address": self.app.config.get("MINTER_WALLET_ADDRESS", "system_minter_address"), # From config
                    "receiver_address": receiver_address,
                    "metadata": goodwill_action.contextual_data,
                    # Add other fields needed by Consensus.add_transaction or LedgerEntry
                }
                
                # Step 2: Add transaction to the Consensus system
                # Consensus.add_transaction will store it in current_transactions and return the block number it's targeting.
                index_of_next_block = self.consensus.add_transaction(transaction_data)
                logger.info(f"⛓️ Transaction for GoodwillAction ID {goodwill_action_id} added to Consensus.")

                # Step 3: Simulate getting blockchain tx hash from the custom chain
                # In a real setup, this would be the actual hash returned after the block is mined
                # and the transaction is confirmed on your custom chain.
                custom_blockchain_tx_hash = f"CUSTOM_TX_{uuid.uuid4().hex}" # Placeholder

                if not custom_blockchain_tx_hash: # If blockchain interaction failed (e.g., actual minting failed)
                    msg = f"❌ Custom blockchain minting failed for GoodwillAction ID {goodwill_action_id}."
                    logger.error(msg)
                    goodwill_action.status = 'FAILED_ON_CHAIN_MINT' # Update status
                    return False, msg

                # Step 4: Update GoodwillAction status and internal blockchain_tx_hash
                goodwill_action.mark_issued_on_chain(tx_hash=custom_blockchain_tx_hash)
                session.add(goodwill_action)

                # Step 5: Create LedgerEntry record for this custom blockchain event
                # This reflects the "mint" event on your custom chain
                ledger_entry = LedgerEntry(
                    blockchain_tx_hash=custom_blockchain_tx_hash,
                    goodwill_action_id=goodwill_action.id, # Link to the GoodwillAction
                    transaction_type='MINT_GOODWILL',
                    amount=loves_to_mint,
                    token_symbol='LOVES', # Consistent with your 'loves' coin
                    sender_address=transaction_data["sender_address"],
                    receiver_address=transaction_data["receiver_address"],
                    block_number=index_of_next_block, # Use the block index where it's included
                    block_timestamp=datetime.now(timezone.utc), # Use current time, or actual block time if available
                    status='CONFIRMED', # Assuming it's confirmed once tx_hash is received from your chain
                    metadata=goodwill_action.contextual_data,
                    initiator_user_id=performer_user_id_uuid,
                    receiver_user_id=performer_user_id_uuid,
                )
                session.add(ledger_entry)

                # Step 6: Update UserAccount balance (off-chain cache)
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
