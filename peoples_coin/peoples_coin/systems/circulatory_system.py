# peoples_coin/peoples_coin/systems/circulatory_system.py

import logging
from datetime import datetime, timezone
from sqlalchemy.orm.exc import NoResultFound
import threading
from decimal import Decimal

from peoples_coin.peoples_coin.db.db import db
from peoples_coin.peoples_coin.db.models import GoodwillAction, UserAccount

logger = logging.getLogger(__name__)

class CirculatorySystem:
    _instance = None
    _lock = threading.Lock()

    COMPLETED_STATUS = 'completed'
    TOKEN_ID_PREFIX = 'TPC-Love-'

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self.db = db
            logger.info("CirculatorySystem: Initialized.")
            self._initialized = True

    def calculate_mint_amount(self, resonance_score: int) -> Decimal:
        """
        Calculates the amount of People's Coin (in 'Loves') to mint.
        Returns the amount as a Decimal for precision.
        """
        mint_amount_loves = Decimal(resonance_score)
        logger.info(f"Calculated mint amount of {mint_amount_loves} Loves for resonance score {resonance_score}.")
        return mint_amount_loves

    def _generate_token_id(self, goodwill_action_id: int) -> str:
        """Generates a unique token ID for the minted People's Coin."""
        return f"{self.TOKEN_ID_PREFIX}{goodwill_action_id}"

    def mint_tokens(self, goodwill_action_id: int) -> tuple[bool, str]:
        """
        Atomically mints 'Loves' for a completed GoodwillAction, updating the user's balance.
        This operation is thread-safe and prevents re-minting.
        """
        session = self.db.session
        try:
            # Use session.begin() for automatic transaction commit/rollback
            with session.begin():
                # Step 1: Retrieve the GoodwillAction
                goodwill_action = session.query(GoodwillAction).filter_by(id=goodwill_action_id).one()

                # Step 2: Validate the action's status and ensure it hasn't been minted
                if goodwill_action.status != self.COMPLETED_STATUS:
                    return False, f"GoodwillAction ID {goodwill_action_id} not in '{self.COMPLETED_STATUS}' status."

                if goodwill_action.minted_token_id is not None:
                    return False, f"GoodwillAction ID {goodwill_action_id} already minted."

                user_id = goodwill_action.user_id
                resonance_score = goodwill_action.resonance_score
                mint_amount_loves = self.calculate_mint_amount(resonance_score)

                # Step 3: Get or create the UserAccount with a row-level lock
                try:
                    # CRITICAL FIX: Use with_for_update() to lock the row and prevent race conditions
                    user_account = session.query(UserAccount).filter_by(user_id=user_id).with_for_update().one()
                    logger.info(f"Found and locked UserAccount for {user_id}.")
                except NoResultFound:
                    user_account = UserAccount(user_id=user_id, balance=Decimal('0.0'))
                    session.add(user_account)
                    logger.info(f"Created new UserAccount for {user_id}.")

                # Step 4: Update balance and mark action as minted
                user_account.balance += mint_amount_loves
                goodwill_action.minted_token_id = self._generate_token_id(goodwill_action_id)
                # The 'updated_at' fields on both models are handled automatically by the 'onupdate' parameter

            # The transaction is automatically committed here if no exceptions were raised
            logger.info(f"Successfully minted {mint_amount_loves} Loves for user '{user_id}'. New balance: {user_account.balance:.4f} Loves.")
            return True, f"Minted {mint_amount_loves} Loves. New balance: {user_account.balance:.4f} Loves."

        except NoResultFound:
            logger.error(f"GoodwillAction with ID {goodwill_action_id} not found for minting.")
            return False, f"GoodwillAction ID {goodwill_action_id} not found."
        except Exception as e:
            logger.critical(f"Error minting tokens for GoodwillAction ID {goodwill_action_id}: {e}", exc_info=True)
            return False, f"An unexpected error occurred during minting: {str(e)}"
