from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from decimal import Decimal

from sqlalchemy.orm import Query, relationship
from sqlalchemy import event

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
        return super().filter(self._only_not_deleted()).get(ident)

    def _only_not_deleted(self):
        """Return filter condition for non-deleted rows if model has deleted_at."""
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
    """Base model that applies soft delete filtering on queries."""
    __abstract__ = True
    query_class = SoftDeleteQuery
    query: SoftDeleteQuery

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)


# ==============================================================================
# 3. Mixins for common columns
# ==============================================================================

class TimestampMixin:
    """
    Adds created_at and updated_at timestamp columns with UTC timezone awareness.
    """
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class SoftDeleteMixin:
    """Adds a soft delete timestamp column."""
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)


# ==============================================================================
# 4. Application Models with Enhancements
# ==============================================================================

class DataEntry(BaseModel, TimestampMixin, SoftDeleteMixin):
    """
    Stores arbitrary data entries, with a processed flag.
    """
    __tablename__ = 'data_entries'
    __table_args__ = (db.Index('idx_processed_created_at', 'processed', 'created_at'),)

    value = db.Column(db.Text, nullable=True)
    processed = db.Column(db.Boolean, default=False, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'value': self.value,
            'processed': self.processed,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None,
        }

    def __repr__(self) -> str:
        return f"<DataEntry id={self.id} processed={self.processed}>"


class UserAccount(BaseModel, TimestampMixin, SoftDeleteMixin):
    """
    Represents a user's account holding their balance in 'Loves'.
    """
    __tablename__ = 'user_accounts'

    user_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    balance = db.Column(db.Numeric(precision=18, scale=4), default=Decimal('0.0'), nullable=False)

    # Relationship to GoodwillAction
    goodwill_actions = relationship("GoodwillAction", back_populates="user_account", lazy='dynamic')

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "balance": str(self.balance),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }

    def __repr__(self) -> str:
        return f"<UserAccount user_id={self.user_id} balance={self.balance}>"


class GoodwillAction(BaseModel, SoftDeleteMixin):
    """
    Represents a verified goodwill action. Includes status and resonance scoring.
    """
    __tablename__ = 'goodwill_actions'
    __table_args__ = (db.Index('idx_goodwill_status', 'status'),)

    user_id = db.Column(db.String(255), db.ForeignKey('user_accounts.user_id'), nullable=False, index=True)
    action_type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    contextual_data = db.Column(db.JSON, default=dict)
    raw_goodwill_score = db.Column(db.Integer, default=0, nullable=False)
    resonance_score = db.Column(db.Float, nullable=True)

    initial_model_state_v0 = db.Column(db.Float, nullable=True)
    expected_workload_intensity_w0 = db.Column(db.Float, nullable=True)
    client_compute_estimate = db.Column(db.Float, nullable=True)

    status = db.Column(db.String(50), default='pending', nullable=False)
    processed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    minted_token_id = db.Column(db.String(255), nullable=True, unique=True)

    correlation_id = db.Column(db.String(255), nullable=True)

    # Relationship back to UserAccount
    user_account = relationship("UserAccount", back_populates="goodwill_actions", lazy='joined')

    def mark_processed(self) -> None:
        """
        Marks the goodwill action as processed, setting timestamp.
        """
        self.status = 'completed'
        self.processed_at = utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action_type": self.action_type,
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
            "contextual_data": self.contextual_data,
            "raw_goodwill_score": self.raw_goodwill_score,
            "resonance_score": self.resonance_score,
            "initial_model_state_v0": self.initial_model_state_v0,
            "expected_workload_intensity_w0": self.expected_workload_intensity_w0,
            "client_compute_estimate": self.client_compute_estimate,
            "status": self.status,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "minted_token_id": self.minted_token_id,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "correlation_id": self.correlation_id,
        }

    def __repr__(self) -> str:
        return (
            f"<GoodwillAction id={self.id} status={self.status} "
            f"user_id={self.user_id} correlation_id={self.correlation_id}>"
        )


class EventLog(BaseModel):
    """Logs significant events within the system."""
    __tablename__ = 'event_logs'
    __table_args__ = (db.Index('idx_event_type_timestamp', 'event_type', 'timestamp'),)

    event_type = db.Column(db.String(64), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<EventLog id={self.id} event_type={self.event_type}>"


# ==============================================================================
# 5. Consensus System Models (unchanged)
# ==============================================================================

class ConsensusNode(BaseModel):
    """Represents a registered node in the consensus network."""
    __tablename__ = 'consensus_nodes'

    id = db.Column(db.String(255), primary_key=True)
    address = db.Column(db.String(255), unique=True, nullable=False)
    registered_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "address": self.address,
            "registered_at": self.registered_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<ConsensusNode id={self.id} address={self.address}>"


class ChainBlock(BaseModel):
    """Represents a single block in the blockchain."""
    __tablename__ = 'chain_blocks'

    timestamp = db.Column(db.Float, nullable=False)
    transactions = db.Column(db.JSON, nullable=False)
    previous_hash = db.Column(db.String(64), nullable=False)
    nonce = db.Column(db.Integer, default=0, nullable=False)
    hash = db.Column(db.String(64), unique=True, nullable=False, index=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.id,
            "timestamp": self.timestamp,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
        }

    def __repr__(self) -> str:
        return f"<ChainBlock index={self.id} hash={self.hash[:8]}...>"


# ==============================================================================
# 6. Event Listener Examples for Validation & Defaults
# ==============================================================================

@event.listens_for(GoodwillAction, "before_insert")
def goodwill_before_insert(mapper, connection, target: GoodwillAction) -> None:
    """
    Example validation to ensure status is always set properly.
    """
    if target.status not in ('pending', 'completed', 'failed'):
        target.status = 'pending'


@event.listens_for(UserAccount.balance, "set", retval=False)
def balance_set(target: UserAccount, value, oldvalue, initiator):
    """
    Prevent negative balances at assignment.
    """
    if value is not None and value < 0:
        raise ValueError("UserAccount balance cannot be negative.")
    return value

