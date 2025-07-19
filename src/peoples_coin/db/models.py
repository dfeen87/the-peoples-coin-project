from datetime import datetime, timezone
from typing import Dict, Any, Optional
import uuid

from sqlalchemy.orm import Query, relationship
from sqlalchemy import event, Column, String, Boolean, DateTime, ForeignKey, Integer, Float, Text, Numeric, CheckConstraint, Index, UniqueConstraint, BigInteger, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import JSONB
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

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("uuid_generate_v4()"))

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.id}>"


# ==============================================================================
# 3. Mixins for common columns
# ==============================================================================

class TimestampMixin:
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, server_default=text("now()"))
    updated_at = Column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False, server_default=text("now()")
    )


class SoftDeleteMixin:
    deleted_at = Column(DateTime(timezone=True), nullable=True, default=None)
    deleted_by = Column(PG_UUID(as_uuid=True), nullable=True, index=True)
    # You can add deletion audit logic on your app side to set deleted_by when soft deleting.


# ==============================================================================
# 4. Application Models with Enhancements
# ==============================================================================

class DataEntry(BaseModel, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'data_entries'
    __table_args__ = (
        Index('idx_processed_created_at', 'processed', 'created_at'),
        {'extend_existing': True},
    )

    value = Column(Text, nullable=True)
    processed = Column(Boolean, default=False, nullable=False, server_default=text('false'))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': str(self.id),
            'value': self.value,
            'processed': self.processed,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None,
        }

    def __repr__(self) -> str:
        return f"<DataEntry id={self.id} processed={self.processed}>"


class UserAccount(BaseModel, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'users'

    firebase_uid = Column(String(128), unique=True, nullable=False, index=True)
    balance = Column(Numeric(precision=20, scale=8), default=0, nullable=False, server_default=text('0'))
    is_premium = Column(Boolean, default=False, nullable=False, server_default=text('false'))  # For frontend features

    # Relationships
    goodwill_actions = relationship("GoodwillAction", back_populates="user_account", lazy='dynamic',
                                    primaryjoin="UserAccount.id == GoodwillAction.performer_user_id")
    api_keys = relationship("ApiKey", back_populates="user_account", cascade="all, delete-orphan",
                            primaryjoin="UserAccount.id == ApiKey.user_id")
    user_wallets = relationship("UserWallet", back_populates="user_account", lazy='dynamic', cascade="all, delete-orphan",
                                primaryjoin="UserAccount.id == UserWallet.user_id")
    proposals = relationship("Proposal", back_populates="proposer", lazy='dynamic',
                             primaryjoin="UserAccount.id == Proposal.proposer_user_id")
    votes = relationship("Vote", back_populates="voter", lazy='dynamic',
                         primaryjoin="UserAccount.id == Vote.voter_user_id")
    council_memberships = relationship("CouncilMember", back_populates="user_account", lazy='dynamic',
                                       primaryjoin="UserAccount.id == CouncilMember.user_id")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "firebase_uid": self.firebase_uid,
            "balance": str(self.balance),
            "is_premium": self.is_premium,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }

    def __repr__(self) -> str:
        return f"<UserAccount id={self.id} firebase_uid={self.firebase_uid} balance={self.balance}>"


class UserWallet(BaseModel, TimestampMixin):
    __tablename__ = 'user_wallets'

    user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    public_address = Column(String(42), unique=True, nullable=False)
    blockchain_network = Column(String(50), nullable=False, default='Ethereum Mainnet', server_default=text("'Ethereum Mainnet'"))
    is_primary = Column(Boolean, default=False, nullable=False, server_default=text('false'))

    user_account = relationship("UserAccount", back_populates="user_wallets")

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


class GoodwillAction(BaseModel, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'goodwill_actions'
    __table_args__ = (
        Index('idx_goodwill_status', 'status'),
        Index('idx_goodwill_performer', 'performer_user_id'),
        {'extend_existing': True},
        CheckConstraint(
            "status IN ('PENDING_VERIFICATION', 'VERIFIED', 'ISSUED_ON_CHAIN', 'FAILED_ON_CHAIN_MINT', 'FAILED_WALLET_MISSING', 'FAILED_DISPATCH', 'FAILED_ENDOCRINE_BATCH')",
            name="chk_goodwill_status_valid"
        ),
        CheckConstraint(
            "loves_value BETWEEN 1 AND 100",
            name="chk_goodwill_loves_value_range"
        ),
    )

    performer_user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    action_type = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    contextual_data = Column(JSONB, default=dict, nullable=False, server_default=text("'{}'::jsonb"))
    loves_value = Column(Integer, default=0, nullable=False)
    resonance_score = Column(Float, nullable=True)

    initial_model_state_v0 = Column(Float, nullable=True)
    expected_workload_intensity_w0 = Column(Float, nullable=True)
    client_compute_estimate = Column(Float, nullable=True)

    status = Column(String(50), default='PENDING_VERIFICATION', nullable=False, server_default=text("'PENDING_VERIFICATION'"))
    processed_at = Column(DateTime(timezone=True), nullable=True)
    blockchain_tx_hash = Column(String(66), nullable=True, unique=True)

    correlation_id = Column(String(255), nullable=True)

    user_account = relationship("UserAccount", back_populates="goodwill_actions", lazy='joined',
                                primaryjoin="GoodwillAction.performer_user_id == UserAccount.id")

    def mark_issued_on_chain(self, tx_hash: str) -> None:
        self.status = 'ISSUED_ON_CHAIN'
        self.blockchain_tx_hash = tx_hash
        self.processed_at = utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "performer_user_id": str(self.performer_user_id),
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
            "deleted_by": str(self.deleted_by) if self.deleted_by else None,
            "correlation_id": self.correlation_id,
        }

    def __repr__(self) -> str:
        return (
            f"<GoodwillAction id={self.id} status={self.status} "
            f"performer_user_id={self.performer_user_id}>"
        )


class LedgerEntry(BaseModel, TimestampMixin):
    __tablename__ = 'ledger_entries'
    __table_args__ = (
        Index('idx_ledger_tx_hash', 'blockchain_tx_hash'),
        Index('idx_ledger_block_time', 'block_timestamp', postgresql_using='btree'),
        Index('idx_ledger_sender_receiver', 'sender_address', 'receiver_address'),
        {'extend_existing': True},
    )

    blockchain_tx_hash = Column(String(66), unique=True, nullable=False, index=True)
    goodwill_action_id = Column(PG_UUID(as_uuid=True), ForeignKey('goodwill_actions.id'), nullable=True, unique=True, index=True)

    transaction_type = Column(String(50), nullable=False)
    amount = Column(Numeric(precision=20, scale=8), nullable=False)
    token_symbol = Column(String(10), nullable=False, default='GOODWILL', server_default=text("'GOODWILL'"))
    sender_address = Column(String(42), nullable=False)
    receiver_address = Column(String(42), nullable=False)
    block_number = Column(BigInteger, nullable=False, index=True)
    block_timestamp = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), nullable=False, default='CONFIRMED', server_default=text("'CONFIRMED'"))
    metadata = Column(JSONB, default=dict, nullable=True, server_default=text("'{}'::jsonb"))

    initiator_user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=True, index=True)
    receiver_user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=True, index=True)

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


class EventLog(BaseModel, TimestampMixin):
    __tablename__ = 'event_logs'
    __table_args__ = (
        Index('idx_event_type_timestamp', 'event_type', 'created_at'),
        {'extend_existing': True},
    )

    event_type = Column(String(64), nullable=False, index=True)
    message = Column(Text, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "event_type": self.event_type,
            "message": self.message,
            "timestamp": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<EventLog id={self.id} event_type={self.event_type}>"


# ==============================================================================
# 5. Consensus System Models
# ==============================================================================

class ConsensusNode(BaseModel, TimestampMixin):
    __tablename__ = 'consensus_nodes'
    __table_args__ = {'extend_existing': True}

    address = Column(String(255), unique=True, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "address": self.address,
            "registered_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<ConsensusNode id={self.id} address={self.address}>"


class ChainBlock(BaseModel):
    __tablename__ = 'chain_blocks'
    __table_args__ = {'extend_existing': True}

    block_number = Column(Integer, unique=True, nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    previous_hash = Column(String(64), nullable=False)
    nonce = Column(Integer, default=0, nullable=False, server_default=text('0'))
    hash = Column(String(64), unique=True, nullable=False, index=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
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

class ApiKey(BaseModel, TimestampMixin):
    __tablename__ = "api_keys"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("uuid_generate_v4()"))
    key = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False, server_default=text('false'))

    user_account = relationship("UserAccount", back_populates="api_keys",
                                primaryjoin="ApiKey.user_id == UserAccount.id")

    def __repr__(self):
        return f"<ApiKey {self.key} user_id={self.user_id} revoked={self.revoked}>"


# ==============================================================================
# 7. Governance System Models (NEW)
# ==============================================================================

class Proposal(BaseModel, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'proposals'
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'VOTING', 'PASSED', 'FAILED', 'EXECUTED')",
            name='chk_proposal_status_valid'
        ),
        {'extend_existing': True},
    )

    proposer_user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(50), default='DRAFT', nullable=False, server_default=text("'DRAFT'"))
    vote_start_time = Column(DateTime(timezone=True), nullable=True)
    vote_end_time = Column(DateTime(timezone=True), nullable=True)
    required_quorum = Column(Numeric(precision=5, scale=2), default=0, nullable=False, server_default=text('0'))  # Between 0.0 and 1.0
    proposal_type = Column(String(100), nullable=False)  # e.g., PROTOCOL_CHANGE, TREASURY_SPEND, COUNCIL_ELECTION
    details = Column(JSONB, default=dict, nullable=True, server_default=text("'{}'::jsonb"))

    proposer = relationship("

