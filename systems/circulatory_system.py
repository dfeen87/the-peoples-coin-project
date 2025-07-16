import logging
from datetime import datetime, timezone
from sqlalchemy.orm.exc import NoResultFound
from decimal import Decimal, InvalidOperation
from typing import Tuple, Optional

from flask import Flask

from peoples_coin.db.db_utils import get_session_scope
from peoples_coin.db.models import GoodwillAction, UserAccount

logger = logging.getLogger(__name__)


class CirculatorySystem:
    """
    Handles the core logic of token minting based on completed goodwill actions.
    Designed to be initialized as a Flask extension.
    """

    def __init__(self):
        self.app: Optional[Flask] = None
        self.db = None
        self.token_prefix: str = 'TPC-Love-'
        self._initialized = False
        logger.info("🫀 CirculatorySystem instance created.")

    def init_app(self, app: Flask, db):
        if self._initialized:
            return

        self.app = app
        self.db = db
        app.config.setdefault("CIRCULATORY_TOKEN_PREFIX", "TPC-Love-")
        self.token_prefix = app.config["CIRCULATORY_TOKEN_PREFIX"]

        self._initialized = True
        logger.info("🫀 CirculatorySystem initialized and configured.")

    def calculate_mint_amount(self, resonance_score: Optional[int]) -> Decimal:
        """
        Calculates the amount of People's Coin to mint from a resonance_score.

        Args:
            resonance_score: The resonance score of the goodwill action.

        Returns:
            Decimal representing minted Loves. Defaults to 0 if invalid.
        """
        try:
            if resonance_score is None or resonance_score < 0:
                raise ValueError("Invalid or missing resonance_score.")
            mint_amount_loves = Decimal(resonance_score)
            logger.debug(f"🧮 Calculated mint amount {mint_amount_loves} Loves for resonance score {resonance_score}.")
            return mint_amount_loves
        except (InvalidOperation, ValueError) as e:
            logger.warning(f"⚠️ Failed to calculate mint amount: {e}. Defaulting to 0.")
            return Decimal('0.0')

    def _generate_token_id(self, goodwill_action_id: int) -> str:
        token_id = f"{self.token_prefix}{goodwill_action_id}"
        logger.debug(f"🔖 Generated token ID: {token_id}")
        return token_id

    def mint_tokens(self, goodwill_action_id: int) -> Tuple[bool, str]:
        """
        Atomically mints 'Loves' for a completed GoodwillAction, creating or updating the user's balance.

        Args:
            goodwill_action_id: The ID of the GoodwillAction to process.

        Returns:
            Tuple with success flag & descriptive message.
        """
        if not self._initialized:
            msg = "🛑 CirculatorySystem has not been initialized."
            logger.error(msg)
            return False, msg

        with get_session_scope() as session:
            try:
                goodwill_action = session.query(GoodwillAction).filter_by(id=goodwill_action_id).one()

                # Idempotency: status check
                if goodwill_action.status != 'completed':
                    msg = f"⏩ Mint skipped: GoodwillAction ID {goodwill_action_id} status='{goodwill_action.status}'."
                    logger.warning(msg)
                    return False, msg

                # Idempotency: already minted
                if goodwill_action.minted_token_id is not None:
                    msg = f"⏩ Mint skipped: GoodwillAction ID {goodwill_action_id} already minted as {goodwill_action.minted_token_id}."
                    logger.warning(msg)
                    return False, msg

                user_id = goodwill_action.user_id
                resonance_score = goodwill_action.resonance_score
                mint_amount_loves = self.calculate_mint_amount(resonance_score)

                # Lock or create user account
                try:
                    user_account = (
                        session.query(UserAccount)
                        .filter_by(user_id=user_id)
                        .with_for_update()
                        .one()
                    )
                    logger.debug(f"🔒 Locked UserAccount for user_id {user_id}.")
                except NoResultFound:
                    user_account = UserAccount(user_id=user_id, balance=Decimal('0.0'))
                    session.add(user_account)
                    logger.info(f"👤 Created new UserAccount for user_id {user_id}.")

                # Mint
                user_account.balance += mint_amount_loves
                goodwill_action.minted_token_id = self._generate_token_id(goodwill_action_id)

                msg = (
                    f"✅ Successfully minted {mint_amount_loves:.4f} Loves for user {user_id}. "
                    f"New balance: {user_account.balance:.4f}."
                )
                logger.info(msg)
                return True, msg

            except NoResultFound:
                msg = f"❌ Minting failed: GoodwillAction ID {goodwill_action_id} not found."
                logger.error(msg)
                return False, msg

            except Exception as e:
                logger.error(
                    f"💥 Unexpected error minting for GoodwillAction ID {goodwill_action_id}: {e}",
                    exc_info=True
                )
                return False, "An internal error occurred during minting."


# Singleton instance
circulatory_system = CirculatorySystem()
