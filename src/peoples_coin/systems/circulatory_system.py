import logging
from datetime import datetime, timezone
from sqlalchemy.orm.exc import NoResultFound
from decimal import Decimal
from typing import Tuple, Optional

from flask import Flask

# Assuming these utilities and models exist from previous files
from ..db.db_utils import get_session_scope
from ..db.models import GoodwillAction, UserAccount

logger = logging.getLogger(__name__)

class CirculatorySystem:
    """
    Handles the core logic of token minting based on completed goodwill actions.
    Designed to be initialized as a Flask extension.
    """

    def __init__(self):
        """Initializes the system's state."""
        self.app: Optional[Flask] = None
        self.db = None
        self.token_prefix: str = 'TPC-Love-'
        self._initialized = False
        logger.info("CirculatorySystem instance created.")

    def init_app(self, app: Flask, db):
        """
        Initializes the Circulatory System with the Flask app and database extension.

        Args:
            app: The Flask application instance.
            db: The Flask-SQLAlchemy database instance.
        """
        if self._initialized:
            return

        self.app = app
        self.db = db
        
        # Load configuration from the app context
        app.config.setdefault("CIRCULATORY_TOKEN_PREFIX", "TPC-Love-")
        self.token_prefix = app.config["CIRCULATORY_TOKEN_PREFIX"]
        
        self._initialized = True
        logger.info("CirculatorySystem initialized and configured.")

    def calculate_mint_amount(self, resonance_score: int) -> Decimal:
        """
        Calculates the amount of People's Coin (in 'Loves') to mint.
        This can be expanded with more complex logic (e.g., curves, multipliers).

        Args:
            resonance_score: The score assigned to the goodwill action.

        Returns:
            The amount to mint as a Decimal for precision.
        """
        # Using Decimal ensures precision for financial calculations.
        mint_amount_loves = Decimal(resonance_score)
        logger.debug(f"Calculated mint amount {mint_amount_loves} Loves for resonance score {resonance_score}.")
        return mint_amount_loves

    def _generate_token_id(self, goodwill_action_id: int) -> str:
        """Generates a unique, descriptive token ID for the minted People's Coin."""
        token_id = f"{self.token_prefix}{goodwill_action_id}"
        logger.debug(f"Generated token ID: {token_id}")
        return token_id

    def mint_tokens(self, goodwill_action_id: int) -> Tuple[bool, str]:
        """
        Atomically mints 'Loves' for a completed GoodwillAction, creating or
        updating the user's balance. This operation is idempotent and thread-safe.

        Args:
            goodwill_action_id: The ID of the GoodwillAction to process.

        Returns:
            A tuple containing a success flag and a descriptive message.
        """
        if not self._initialized:
            msg = "CirculatorySystem has not been initialized with a Flask app."
            logger.error(msg)
            return False, msg

        # Use the explicit session scope for guaranteed isolation and cleanup.
        with get_session_scope() as session:
            try:
                # Fetch the goodwill action to be processed.
                goodwill_action = session.query(GoodwillAction).filter_by(id=goodwill_action_id).one()

                # Idempotency Check 1: Ensure the action is in the correct state.
                if goodwill_action.status != 'completed':
                    msg = f"Minting skipped: GoodwillAction ID {goodwill_action_id} has status '{goodwill_action.status}', not 'completed'."
                    logger.warning(msg)
                    return False, msg

                # Idempotency Check 2: Ensure tokens haven't already been minted for this action.
                if goodwill_action.minted_token_id is not None:
                    msg = f"Minting skipped: GoodwillAction ID {goodwill_action_id} already minted with token ID {goodwill_action.minted_token_id}."
                    logger.warning(msg)
                    return False, msg

                user_id = goodwill_action.user_id
                resonance_score = goodwill_action.resonance_score
                mint_amount_loves = self.calculate_mint_amount(resonance_score)

                # Fetch or create the user's account with a row-level lock to prevent race conditions.
                try:
                    user_account = session.query(UserAccount).filter_by(user_id=user_id).with_for_update().one()
                    logger.debug(f"Locked UserAccount for user_id {user_id}.")
                except NoResultFound:
                    user_account = UserAccount(user_id=user_id, balance=Decimal('0.0'))
                    session.add(user_account)
                    logger.info(f"Created new UserAccount for user_id {user_id}.")

                # Perform the minting operations.
                user_account.balance += mint_amount_loves
                goodwill_action.minted_token_id = self._generate_token_id(goodwill_action_id)
                
                # The session commit is handled by the get_session_scope context manager.
                msg = f"Successfully minted {mint_amount_loves:.4f} Loves for user {user_id}. New balance: {user_account.balance:.4f}."
                logger.info(msg)
                return True, msg

            except NoResultFound:
                msg = f"Minting failed: GoodwillAction with ID {goodwill_action_id} not found."
                logger.error(msg)
                return False, msg
            except Exception as e:
                # Log the detailed, specific error for debugging purposes.
                logger.error(f"Unexpected error minting for GoodwillAction ID {goodwill_action_id}: {e}", exc_info=True)
                # Return a generic, safe message to the caller.
                return False, "An unexpected internal error occurred during the minting process."

