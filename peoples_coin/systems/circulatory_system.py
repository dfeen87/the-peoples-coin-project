# peoples_coin/systems/circulatory_system.py

import logging
import http
import uuid
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Tuple, Optional

from flask import Flask
from sqlalchemy.orm.exc import NoResultFound

from peoples_coin.utils.auth import require_api_key
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models import GoodwillAction, UserAccount, LedgerEntry, UserWallet
from peoples_coin.consensus import Consensus
from peoples_coin.extensions import db

logger = logging.getLogger(__name__)

class CirculatorySystem:
    """Handles the core logic of token minting based on completed goodwill actions."""

    def __init__(self):
        self.app: Optional[Flask] = None
        self.consensus: Optional[Consensus] = None
        self.minter_wallet_address: Optional[str] = None
        self._initialized = False
        logger.info("🫀 CirculatorySystem instance created.")

    def init_app(self, app: Flask, consensus_instance: Consensus):
        """Initializes the system with the Flask app and dependencies."""
        if self._initialized:
            return
        self.app = app
        self.db = db
        self.consensus = consensus_instance
        
        # Use environment variable instead of app config to avoid missing env on Cloud Run
        self.minter_wallet_address = os.getenv("MINTER_WALLET_ADDRESS")
        
        if not self.minter_wallet_address:
            raise RuntimeError("MINTER_WALLET_ADDRESS must be configured in the environment.")
        
        self._initialized = True
        logger.info("🫀 CirculatorySystem initialized and configured.")

    def process_goodwill_for_minting(self, goodwill_action_id: uuid.UUID) -> Tuple[bool, str, int]:
        """Processes a verified GoodwillAction for minting."""
        if not self._initialized or not self.consensus:
            msg = "CirculatorySystem or Consensus has not been properly initialized."
            logger.critical(msg)
            return False, msg, http.HTTPStatus.INTERNAL_SERVER_ERROR

        with get_session_scope(self.db) as session:
            try:
                goodwill_action = session.query(GoodwillAction).with_for_update().filter_by(id=goodwill_action_id).one()

                if goodwill_action.status == 'ISSUED_ON_CHAIN':
                    msg = f"Skipped: GoodwillAction {goodwill_action_id} already issued on-chain."
                    return True, msg, http.HTTPStatus.OK

                if goodwill_action.status != 'VERIFIED':
                    msg = f"Skipped: GoodwillAction {goodwill_action_id} status is '{goodwill_action.status}', not 'VERIFIED'."
                    return False, msg, http.HTTPStatus.UNPROCESSABLE_ENTITY

                user_account = session.query(UserAccount).filter_by(id=goodwill_action.performer_user_id).first()
                if not user_account:
                    msg = f"Minting failed: UserAccount not found for performer ID {goodwill_action.performer_user_id}."
                    goodwill_action.status = 'FAILED_USER_NOT_FOUND'
                    return False, msg, http.HTTPStatus.UNPROCESSABLE_ENTITY

                user_wallet = session.query(UserWallet).filter_by(user_id=user_account.id, is_primary=True).first()
                if not user_wallet:
                    msg = f"Minting failed: No primary wallet found for user ID {user_account.id}."
                    goodwill_action.status = 'FAILED_WALLET_MISSING'
                    return False, msg, http.HTTPStatus.UNPROCESSABLE_ENTITY

                loves_to_mint = Decimal(goodwill_action.loves_value)
                now_utc = datetime.now(timezone.utc)

                transaction_data = { "action_id": str(goodwill_action.id), "amount": float(loves_to_mint) }
                index_of_next_block = self.consensus.add_transaction(transaction_data)
                custom_blockchain_tx_hash = f"CUSTOM_TX_{uuid.uuid4().hex}"

                goodwill_action.mark_issued_on_chain(tx_hash=custom_blockchain_tx_hash)
                user_account.balance += loves_to_mint
                
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
                    initiator_user_id=user_account.id,
                    receiver_user_id=user_account.id,
                )
                session.add(ledger_entry)
                
                msg = f"Successfully minted {loves_to_mint:.4f} Loves for user {user_account.id}."
                logger.info(msg)
                return True, msg, http.HTTPStatus.OK

            except NoResultFound:
                msg = f"Minting failed: GoodwillAction ID {goodwill_action_id} not found."
                return False, msg, http.HTTPStatus.NOT_FOUND
            except Exception as e:
                logger.exception(f"Unexpected error processing mint for GoodwillAction ID {goodwill_action_id}: {e}")
                return False, "An internal error occurred during minting.", http.HTTPStatus.INTERNAL_SERVER_ERROR

# Singleton Instance
circulatory_system = CirculatorySystem()

# --- Function for status page ---
def get_circulatory_status():
    """Health check for the Circulatory System."""
    if circulatory_system._initialized:
        return {"active": True, "healthy": True, "info": "Circulatory System operational"}
    else:
        return {"active": False, "healthy": False, "info": "Circulatory System not initialized"}

