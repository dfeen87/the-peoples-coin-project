from datetime import datetime, timezone
from typing import Dict, Any, Optional
from decimal import Decimal
import uuid

from sqlalchemy.orm import Query, relationship
from sqlalchemy import event, Column, String, Boolean, DateTime, ForeignKey, Integer, Float, Text, Numeric, JSON
from sqlalchemy.dialects.postgresql import UUID

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

    id = Column(Integer, primary_key=True, autoincrement=True)

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
    __tablename__ = 'user_accounts'

    user_id = Column(String(255), unique=True, nullable=False, index=True)
    balance = Column(Numeric(precision=18, scale=4), default=Decimal('0.0'), nullable=False)

    goodwill_actions = relationship("GoodwillAction", back_populates="user_account", lazy='dynamic')
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")

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
    __tablename__ = 'goodwill_actions'
    __table_args__ = (
        db.Index('idx_goodwill_status', 'status'),
        {'extend_existing': True},
    )

    user_id = Column(String(255), ForeignKey('user_accounts.user_id'), nullable=False, index=True)
    action_type = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    contextual_data = Column(JSON, default=dict)
    raw_goodwill_score = Column(Integer, default=0, nullable=False)
    resonance_score = Column(Float, nullable=True)

    initial_model_state_v0 = Column(Float, nullable=True)
    expected_workload_intensity_w0 = Column(Float, nullable=True)
    client_compute_estimate = Column(Float, nullable=True)

    status = Column(String(50), default='pending', nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    minted_token_id = Column(String(255), nullable=True, unique=True)

    correlation_id = Column(String(255), nullable=True)

    user_account = relationship("UserAccount", back_populates="goodwill_actions", lazy='joined')

    def mark_processed(self) -> None:
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
    __tablename__ = 'event_logs'
    __table_args__ = (
        db.Index('idx_event_type_timestamp', 'event_type', 'timestamp'),
        {'extend_existing': True},
    )

    event_type = Column(String(64), nullable=False, index=True)
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False)

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
# 5. Consensus System Models
# ==============================================================================

class ConsensusNode(BaseModel):
    __tablename__ = 'consensus_nodes'
    __table_args__ = {'extend_existing': True}

    id = Column(String(255), primary_key=True)
    address = Column(String(255), unique=True, nullable=False)
    registered_at = Column(DateTime(timezone=True), default=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "address": self.address,
            "registered_at": self.registered_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<ConsensusNode id={self.id} address={self.address}>"


class ChainBlock(BaseModel):
    __tablename__ = 'chain_blocks'
    __table_args__ = {'extend_existing': True}

    timestamp = Column(Float, nullable=False)
    transactions = Column(JSON, nullable=False)
    previous_hash = Column(String(64), nullable=False)
    nonce = Column(Integer, default=0, nullable=False)
    hash = Column(String(64), unique=True, nullable=False, index=True)

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
# 6. API Key Model for Authentication
# ==============================================================================

class ApiKey(BaseModel):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("user_accounts.id"), nullable=False)
    created_at = Column(DateTime, default=utcnow)
    revoked = Column(Boolean, default=False)

    user = relationship("UserAccount", back_populates="api_keys")

    def __repr__(self):
        return f"<ApiKey {self.key} user={self.user_id} revoked={self.revoked}>"


# ==============================================================================
# 7. Event Listeners & Validation Hooks
# ==============================================================================

@event.listens_for(GoodwillAction, "before_insert")
def goodwill_before_insert(mapper, connection, target: GoodwillAction) -> None:
    if target.status not in ('pending', 'completed', 'failed'):
        target.status = 'pending'


@event.listens_for(UserAccount.balance, "set", retval=False)
def balance_set(target: UserAccount, value, oldvalue, initiator):
    if value is not None and value < 0:
        raise ValueError("UserAccount balance cannot be negative.")
    return value

