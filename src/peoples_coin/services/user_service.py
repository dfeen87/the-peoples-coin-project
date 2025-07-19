import logging
from typing import Optional, Dict, Any, Tuple, List
from uuid import UUID
from decimal import Decimal

from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import IntegrityError

from peoples_coin.db.db_utils import get_session_scope
from peoples_coin.db.models import UserAccount, UserWallet
from peoples_coin.extensions import db

try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth_admin
    FIREBASE_ADMIN_AVAILABLE = True
except ImportError:
    firebase_admin = None
    firebase_auth_admin = None
    FIREBASE_ADMIN_AVAILABLE = False

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self):
        self.app = None
        self.db = None
        self._initialized = False
        logger.info("UserService instance created.")

    def init_app(self, app, db_instance):
        if self._initialized:
            logger.warning("UserService already initialized; skipping.")
            return
        self.app = app
        self.db = db_instance
        # Optionally initialize Firebase Admin SDK here if needed
        # if FIREBASE_ADMIN_AVAILABLE and not firebase_admin._apps:
        #     firebase_admin.initialize_app()
        self._initialized = True
        logger.info("UserService initialized and configured.")

    def get_user_by_id(self, user_id: UUID) -> Optional[Dict[str, Any]]:
        """Retrieve user account by internal UUID ID."""
        with get_session_scope(self.db) as session:
            user = session.query(UserAccount).filter_by(id=user_id).first()
            return user.to_dict() if user else None

    def get_user_by_firebase_uid(self, firebase_uid: str) -> Optional[Dict[str, Any]]:
        """Retrieve user account by Firebase UID."""
        with get_session_scope(self.db) as session:
            user = session.query(UserAccount).filter_by(firebase_uid=firebase_uid).first()
            return user.to_dict() if user else None

    def create_or_get_user_account(self, firebase_uid: str, email: str, username: str) -> Tuple[UserAccount, bool]:
        """
        Create a new UserAccount or return existing one.
        Returns tuple: (UserAccount instance, created_flag).
        """
        with get_session_scope(self.db) as session:
            existing_user = session.query(UserAccount).filter_by(firebase_uid=firebase_uid).first()
            if existing_user:
                logger.debug(f"UserService: Existing UserAccount found for Firebase UID {firebase_uid}.")
                return existing_user, False
            try:
                new_user = UserAccount(
                    firebase_uid=firebase_uid,
                    email=email,
                    username=username,
                    balance=Decimal('0.0'),
                    is_premium=False
                )
                session.add(new_user)
                session.flush()  # Assigns ID
                logger.info(f"UserService: Created UserAccount {new_user.id} for Firebase UID {firebase_uid}.")
                return new_user, True
            except IntegrityError:
                session.rollback()
                logger.warning(f"UserService: Race condition creating UserAccount for Firebase UID {firebase_uid}, retrying.")
                user = session.query(UserAccount).filter_by(firebase_uid=firebase_uid).one()
                return user, False
            except Exception:
                logger.exception(f"UserService: Unexpected error creating UserAccount for Firebase UID {firebase_uid}.")
                raise

    def update_user_balance(self, user_id: UUID, amount: Decimal) -> Tuple[bool, str]:
        """Add amount to user's balance atomically."""
        with get_session_scope(self.db) as session:
            try:
                user = session.query(UserAccount).filter_by(id=user_id).with_for_update().one()
                user.balance += amount
                logger.info(f"UserService: Updated balance for user {user_id} by {amount}. New balance: {user.balance}.")
                return True, "Balance updated."
            except NoResultFound:
                logger.warning(f"UserService: User {user_id} not found for balance update.")
                return False, "User not found."
            except Exception as e:
                logger.exception(f"UserService: Error updating balance for user {user_id}.")
                return False, f"Internal error: {e}"

    def link_user_wallet(self, user_id: UUID, public_address: str, blockchain_network: str, is_primary: bool = False) -> Tuple[bool, str]:
        """Link a blockchain wallet to a user. Demotes existing primary wallet if needed."""
        with get_session_scope(self.db) as session:
            try:
                user = session.query(UserAccount).filter_by(id=user_id).first()
                if not user:
                    return False, "User not found."

                if is_primary:
                    # Demote existing primary wallets
                    existing_primary = session.query(UserWallet).filter_by(user_id=user_id, is_primary=True).first()
                    if existing_primary:
                        existing_primary.is_primary = False
                        session.add(existing_primary)

                new_wallet = UserWallet(
                    user_id=user_id,
                    public_address=public_address,
                    blockchain_network=blockchain_network,
                    is_primary=is_primary
                )
                session.add(new_wallet)
                session.flush()
                logger.info(f"UserService: Linked wallet {public_address} to user {user_id}.")
                return True, "Wallet linked successfully."
            except IntegrityError:
                logger.warning(f"UserService: Wallet {public_address} already linked to user {user_id}.")
                return False, "Wallet already linked."
            except Exception as e:
                logger.exception(f"UserService: Error linking wallet {public_address} to user {user_id}.")
                return False, f"Internal error: {e}"

    def get_user_wallets(self, user_id: UUID) -> List[Dict[str, Any]]:
        """Get all wallets linked to the user."""
        with get_session_scope(self.db) as session:
            wallets = session.query(UserWallet).filter_by(user_id=user_id).all()
            return [wallet.to_dict() for wallet in wallets]

    def set_user_premium_status(self, user_id: UUID, is_premium: bool) -> Tuple[bool, str]:
        """Update user's premium status."""
        with get_session_scope(self.db) as session:
            try:
                user = session.query(UserAccount).filter_by(id=user_id).one()
                user.is_premium = is_premium
                logger.info(f"UserService: Set premium status of user {user_id} to {is_premium}.")
                return True, f"Premium status set to {is_premium}."
            except NoResultFound:
                logger.warning(f"UserService: User {user_id} not found for premium status update.")
                return False, "User not found."
            except Exception as e:
                logger.exception(f"UserService: Error setting premium status for user {user_id}.")
                return False, f"Internal error: {e}"


user_service = UserService()

