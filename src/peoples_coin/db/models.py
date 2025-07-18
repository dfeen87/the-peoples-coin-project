from datetime import datetime, timezone
from typing import Dict, Any, Optional
from decimal import Decimal
import uuid

from sqlalchemy.orm import Query, relationship
from sqlalchemy import event, Column, String, Boolean, DateTime, ForeignKey, Integer, Float, Text, Numeric, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID # Use specific PostgreSQL UUID type
from sqlalchemy.dialects.postgresql import JSONB # Use specific PostgreSQL JSONB type

from peoples_coin.extensions import db


def utcnow() -> datetime:
    """Returns the current time in the UTC timezone."""
    return datetime.now(timezone.utc)


# ==============================================================================
# 1. Custom Query class to implement Soft Delete filtering
# ==============================================================================

class SoftDeleteQuery(Query):
    """Custom Query class that filters out soft-deleted records by default."""

    _with_deleted = False

    def __new__(cls, *args, **kwargs):
        obj = super().__new__(cls)
        return obj

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def with_deleted(self):
        """Return a Query that includes soft-deleted rows."""
        self._with_deleted = True
        return self

    def get(self, ident):
        if self._with_deleted:
            return super().get(ident)
        else:
            mapper = self._only_full_mapper_zero("get")
            if mapper is None:
                return None
            pk = mapper.primary_key[0]
            # Ensure the correct type for UUID comparison if PK is UUID
            if isinstance(ident, str) and isinstance(pk.type, PG_UUID):
                ident = uuid.UUID(ident)
            return self.filter(pk == ident, self._only_not_deleted()).one_or_none()


    def _only_not_deleted(self):
        for entity in self._entities:
            ent = getattr(entity, "entity_zero", None)
            if ent is None:
                continue
            cls = getattr(ent, "class_", None)
            if cls is not None and hasattr(cls, "deleted_at"):
                return cls.deleted_at.is_(None)
        return True

    def __iter__(self):
        if self._with_deleted:
            return super().__iter__()
        return super().filter(self._only_not_deleted()).__iter__()


# ==============================================================================
# 2. Base class with custom query for soft delete support
# ==============================================================================

class BaseModel(db.Model):
    __abstract__ = True
    query_class = SoftDeleteQuery
    query: SoftDeleteQuery = db.session.query_property(query_cls=SoftDeleteQuery)

    # Use UUID as default primary key type across models for consistency
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.id}>"


# ==============================================================================
# 3. Mixins for common columns
# ==============================================================================

class TimestampMixin:
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class SoftDeleteMixin:
    deleted_at = Column(DateTime(timezone=True), nullable=True, default=None)


# ==============================================================================
# 4. Application Models with Enhancements
# ==============================================================================

class DataEntry(BaseModel, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'data_entries'
    __table_args__ = (
        db.Index('idx_processed_created_at', 'processed', 'created_at'),
        {'extend_existing': True},
    )

    value = Column(Text, nullable=True)
    processed = Column(Boolean, default=False, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': str(self.id), # Convert UUID to string for JSON serialization
            'value': self.value,
            'processed': self.processed,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None,
        }

    def __repr__(self) -> str:
        return f"<DataEntry id={self.id} processed={self.processed}>"


class UserAccount(BaseModel, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'users' # Renamed table for clarity

    # Changed from String(255) to PG_UUID(as_uuid=True) for consistency, but
    # if Firebase UID is a string, keep it as String(128)
    # user_id = Column(String(255), unique=True, nullable=False, index=True) # Old column
    firebase_uid = Column(String(128), unique=True, nullable=False, index=True) # Use this for Firebase UID

    balance = Column(Numeric(precision=20, scale=8), default=Decimal('0.0'), nullable=False) # Increased precision for 'loves'

    # Relationships
    goodwill_actions = relationship("GoodwillAction", back_populates="user_account", lazy='dynamic',
                                    primaryjoin="UserAccount.id == GoodwillAction.performer_user_id") # Updated relationship link
    api_keys = relationship("ApiKey", back_populates="user_account", cascade="all, delete-orphan",
                            primaryjoin="UserAccount.id == ApiKey.user_id") # Updated relationship link
    user_wallets = relationship("UserWallet", back_populates="user_account", lazy='dynamic', cascade="all, delete-orphan",
                                primaryjoin="UserAccount.id == UserWallet.user_id") # New relationship

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id), # Convert UUID to string
            "firebase_uid": self.firebase_uid,
            "balance": str(self.balance),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }

    def __repr__(self) -> str:
        return f"<UserAccount id={self.id} firebase_uid={self.firebase_uid} balance={self.balance}>"


class UserWallet(BaseModel, TimestampMixin): # New UserWallet model
    __tablename__ = 'user_wallets'

    user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True) # Foreign Key to UserAccount.id
    public_address = Column(String(42), unique=True, nullable=False) # Ethereum address format
    blockchain_network = Column(String(50), nullable=False, default='Ethereum Mainnet')
    is_primary = Column(Boolean, default=False, nullable=False)

    user_account = relationship("UserAccount", back_populates="user_wallets") # Relationship back to UserAccount

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "public_address": self.public_address,
            "blockchain_network": self.blockchain_network,
            "is_primary": self.is_primary,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<UserWallet id={self.id} public_address={self.public_address}>"


class GoodwillAction(BaseModel, TimestampMixin, SoftDeleteMixin): # Added TimestampMixin
    __tablename__ = 'goodwill_actions'
    __table_args__ = (
        db.Index('idx_goodwill_status', 'status'),
        db.Index('idx_goodwill_performer', 'performer_user_id'), # New index
        {'extend_existing': True},
    )

    performer_user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True) # FK to users.id
    action_type = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    # timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False) # Replaced by created_at from TimestampMixin
    contextual_data = Column(JSONB, default={}) # Use JSONB, default to empty dict
    loves_value = Column(Integer, default=0, nullable=False) # Renamed raw_goodwill_score, now directly the 'loves' score
    resonance_score = Column(Float, nullable=True)

    initial_model_state_v0 = Column(Float, nullable=True)
    expected_workload_intensity_w0 = Column(Float, nullable=True)
    client_compute_estimate = Column(Float, nullable=True)

    status = Column(String(50), default='PENDING_VERIFICATION', nullable=False) # More descriptive initial status
    processed_at = Column(DateTime(timezone=True), nullable=True)
    blockchain_tx_hash = Column(String(66), nullable=True, unique=True) # Renamed minted_token_id, 66 chars for hex hash

    correlation_id = Column(String(255), nullable=True)

    user_account = relationship("UserAccount", back_populates="goodwill_actions", lazy='joined',
                                primaryjoin="GoodwillAction.performer_user_id == UserAccount.id") # Updated relationship link

    # Method to update status to "ISSUED_ON_CHAIN" and link to ledger_entry
    def mark_issued_on_chain(self, tx_hash: str) -> None:
        self.status = 'ISSUED_ON_CHAIN'
        self.blockchain_tx_hash = tx_hash
        self.processed_at = utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "performer_user_id": str(self.performer_user_id), # Convert UUID to string
            "action_type": self.action_type,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "contextual_data": self.contextual_data,
            "loves_value": self.loves_value,
            "resonance_score": self.resonance_score,
            "initial_model_state_v0": self.initial_model_state_v0,
            "expected_workload_intensity_w0": self.expected_workload_intensity_w0,
            "client_compute_estimate": self.client_compute_estimate,
            "status": self.status,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "blockchain_tx_hash": self.blockchain_tx_hash,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "correlation_id": self.correlation_id,
        }

    def __repr__(self) -> str:
        return (
            f"<GoodwillAction id={self.id} status={self.status} "
            f"performer_user_id={self.performer_user_id}>"
        )


class LedgerEntry(BaseModel, TimestampMixin): # New LedgerEntry model
    __tablename__ = 'ledger_entries'
    __table_args__ = (
        db.Index('idx_ledger_tx_hash', 'blockchain_tx_hash'),
        db.Index('idx_ledger_block_time', 'block_timestamp', postgresql_using='btree'), # For faster range queries
        db.Index('idx_ledger_sender_receiver', 'sender_address', 'receiver_address'), # For faster address searches
        {'extend_existing': True},
    )

    blockchain_tx_hash = Column(String(66), unique=True, nullable=False, index=True) # CRITICAL: Hash of the actual transaction on the blockchain
    goodwill_action_id = Column(PG_UUID(as_uuid=True), ForeignKey('goodwill_actions.id'), nullable=True, unique=True, index=True) # Link to goodwill_actions

    transaction_type = Column(String(50), nullable=False) # 'MINT_GOODWILL', 'TRANSFER_GOODWILL', 'BURN_GOODWILL', etc.
    amount = Column(Numeric(precision=20, scale=8), nullable=False)
    token_symbol = Column(String(10), nullable=False, default='GOODWILL')
    sender_address = Column(String(42), nullable=False) # Ethereum address format
    receiver_address = Column(String(42), nullable=False) # Ethereum address format
    block_number = Column(BigInteger, nullable=False) # Use BigInteger for block numbers
    block_timestamp = Column(DateTime(timezone=True), nullable=False) # Timestamp from blockchain block
    status = Column(String(20), nullable=False, default='CONFIRMED') # 'CONFIRMED', 'PENDING' (if tracking pre-mined)
    metadata = Column(JSONB) # Additional flexible data for the ledger entry

    # Optional: Link to your internal users if the transaction relates to an app user
    initiator_user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=True, index=True)
    receiver_user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=True, index=True)

    # Relationships
    goodwill_action = relationship("GoodwillAction", backref="ledger_entry", uselist=False,
                                    primaryjoin="LedgerEntry.goodwill_action_id == GoodwillAction.id")
    initiator_user = relationship("UserAccount", foreign_keys=[initiator_user_id], backref="initiated_ledger_entries")
    receiver_user = relationship("UserAccount", foreign_keys=[receiver_user_id], backref="received_ledger_entries")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "blockchain_tx_hash": self.blockchain_tx_hash,
            "goodwill_action_id": str(self.goodwill_action_id) if self.goodwill_action_id else None,
            "transaction_type": self.transaction_type,
            "amount": str(self.amount),
            "token_symbol": self.token_symbol,
            "sender_address": self.sender_address,
            "receiver_address": self.receiver_address,
            "block_number": self.block_number,
            "block_timestamp": self.block_timestamp.isoformat(),
            "status": self.status,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "initiator_user_id": str(self.initiator_user_id) if self.initiator_user_id else None,
            "receiver_user_id": str(self.receiver_user_id) if self.receiver_user_id else None,
        }

    def __repr__(self) -> str:
        return f"<LedgerEntry id={self.id} tx_hash={self.blockchain_tx_hash[:8]}... type={self.transaction_type}>"


class EventLog(BaseModel, TimestampMixin): # Added TimestampMixin
    __tablename__ = 'event_logs'
    __table_args__ = (
        db.Index('idx_event_type_timestamp', 'event_type', 'timestamp'),
        {'extend_existing': True},
    )

    event_type = Column(String(64), nullable=False, index=True)
    message = Column(Text, nullable=False)
    # timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False) # Replaced by created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "event_type": self.event_type,
            "message": self.message,
            "timestamp": self.created_at.isoformat(), # Use created_at
        }

    def __repr__(self) -> str:
        return f"<EventLog id={self.id} event_type={self.event_type}>"


# ==============================================================================
# 5. Consensus System Models
# ==============================================================================

class ConsensusNode(BaseModel, TimestampMixin): # Added TimestampMixin
    __tablename__ = 'consensus_nodes'
    __table_args__ = {'extend_existing': True}

    # id = Column(String(255), primary_key=True) # Changed from String to UUID
    address = Column(String(255), unique=True, nullable=False)
    # registered_at = Column(DateTime(timezone=True), default=utcnow) # Replaced by created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "address": self.address,
            "registered_at": self.created_at.isoformat(), # Use created_at
        }

    def __repr__(self) -> str:
        return f"<ConsensusNode id={self.id} address={self.address}>"


class ChainBlock(BaseModel):
    __tablename__ = 'chain_blocks'
    __table_args__ = {'extend_existing': True}

    # Removed id=Column(Integer, ...) as BaseModel now defines UUID id
    block_number = Column(Integer, unique=True, nullable=False, index=True) # Unique identifier for the block
    timestamp = Column(DateTime(timezone=True), nullable=False) # Use DateTime, not Float for timestamps
    previous_hash = Column(String(64), nullable=False)
    nonce = Column(Integer, default=0, nullable=False)
    hash = Column(String(64), unique=True, nullable=False, index=True)
    # transactions = Column(JSON, nullable=False) # REMOVED: Transactions now go into LedgerEntry table

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id), # Convert UUID to string
            "block_number": self.block_number,
            "timestamp": self.timestamp.isoformat(),
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
        }

    def __repr__(self) -> str:
        return f"<ChainBlock id={self.id} block_number={self.block_number} hash={self.hash[:8]}...>"


# ==============================================================================
# 6. API Key Model for Authentication
# ==============================================================================

class ApiKey(BaseModel, TimestampMixin): # Added TimestampMixin
    __tablename__ = "api_keys"

    # id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4) # Already handled by BaseModel
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False) # FK to users.id
    key = Column(String(64), unique=True, nullable=False, index=True)
    # created_at = Column(DateTime, default=utcnow) # Replaced by TimestampMixin
    revoked = Column(Boolean, default=False)

    user_account = relationship("UserAccount", back_populates="api_keys",
                                primaryjoin="ApiKey.user_id == UserAccount.id") # Updated relationship link

    def __repr__(self):
        return f"<ApiKey {self.key} user_id={self.user_id} revoked={self.revoked}>"


# ==============================================================================
# 7. Event Listeners & Validation Hooks
# ==============================================================================

@event.listens_for(GoodwillAction, "before_insert")
def goodwill_before_insert(mapper, connection, target: GoodwillAction) -> None:
    # Ensure loves_value is within 1-100 range before insert
    if not (1 <= target.loves_value <= 100):
        raise ValueError("Loves value must be between 1 and 100.")
    if target.status not in ('PENDING_VERIFICATION', 'VERIFIED', 'ISSUED_ON_CHAIN', 'REJECTED'):
        target.status = 'PENDING_VERIFICATION'


@event.listens_for(UserAccount.balance, "set", retval=False)
def balance_set(target: UserAccount, value, oldvalue, initiator):
    if value is not None and value < 0:
        raise ValueError("UserAccount balance cannot be negative.")
    return value
