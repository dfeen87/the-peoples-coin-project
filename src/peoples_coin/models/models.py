from datetime import datetime, timezone
import uuid
from typing import Dict, Any

from sqlalchemy.orm import Query, relationship
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Integer, Float, Text,
    Numeric, CheckConstraint, Index, UniqueConstraint, BigInteger, text
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from peoples_coin.extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

# Custom Query class for soft delete filtering
class SoftDeleteQuery(Query):
    _with_deleted = False

    def with_deleted(self):
        self._with_deleted = True
        return self

    def get(self, ident):
        if self._with_deleted:
            return super().get(ident)
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


# Base model with soft delete and custom query
class BaseModel(db.Model):
    __abstract__ = True
    query_class = SoftDeleteQuery
    query: SoftDeleteQuery = db.session.query_property(query_cls=SoftDeleteQuery)

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("uuid_generate_v4()"))

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.id}>"


class TimestampMixin:
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, server_default=text("now()"))
    updated_at = Column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False, server_default=text("now()")
    )


class SoftDeleteMixin:
    deleted_at = Column(DateTime(timezone=True), nullable=True, default=None)
    deleted_by = Column(PG_UUID(as_uuid=True), nullable=True, index=True)

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

# Models below

class UserAccount(BaseModel, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'users'

    firebase_uid = Column(String(128), unique=True, nullable=False, index=True)
    balance = Column(Numeric(20, 8), default=0, nullable=False, server_default=text('0'))
    is_premium = Column(Boolean, default=False, nullable=False, server_default=text('false'))

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
    council_member_profile = relationship("CouncilMember", back_populates="user", uselist=False)

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


class GoodwillAction(BaseModel, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'goodwill_actions'

    performer_user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    action_type = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    contextual_data = Column(JSONB, default=dict, nullable=False, server_default=text("'{}'::jsonb"))
    loves_value = Column(Integer, default=0, nullable=False)
    resonance_score = Column(Float, nullable=True)

    status = Column(String(50), default='PENDING_VERIFICATION', nullable=False, server_default=text("'PENDING_VERIFICATION'"))
    processed_at = Column(DateTime(timezone=True), nullable=True)
    blockchain_tx_hash = Column(String(66), nullable=True, unique=True)

    user_account = relationship("UserAccount", back_populates="goodwill_actions", lazy='joined',
                                primaryjoin="GoodwillAction.performer_user_id == UserAccount.id")

    def mark_issued_on_chain(self, tx_hash: str) -> None:
        self.status = 'ISSUED_ON_CHAIN'
        self.blockchain_tx_hash = tx_hash
        self.processed_at = utcnow()

    def __repr__(self) -> str:
        return f"<GoodwillAction id={self.id} status={self.status} performer_user_id={self.performer_user_id}>"


class UserWallet(BaseModel, TimestampMixin):
    __tablename__ = 'user_wallets'

    user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    public_address = Column(String(42), unique=True, nullable=False)
    blockchain_network = Column(String(50), nullable=False, default='Ethereum Mainnet', server_default=text("'Ethereum Mainnet'"))
    is_primary = Column(Boolean, default=False, nullable=False, server_default=text('false'))

    user_account = relationship("UserAccount", back_populates="user_wallets")

    def __repr__(self) -> str:
        return f"<UserWallet id={self.id} public_address={self.public_address}>"


class LedgerEntry(BaseModel, TimestampMixin):
    __tablename__ = 'ledger_entries'

    blockchain_tx_hash = Column(String(66), unique=True, nullable=False, index=True)
    goodwill_action_id = Column(PG_UUID(as_uuid=True), ForeignKey('goodwill_actions.id'), nullable=True, unique=True, index=True)

    transaction_type = Column(String(50), nullable=False)
    amount = Column(Numeric(20, 8), nullable=False)
    token_symbol = Column(String(10), nullable=False, default='GOODWILL', server_default=text("'GOODWILL'"))
    sender_address = Column(String(42), nullable=False)
    receiver_address = Column(String(42), nullable=False)
    block_number = Column(BigInteger, nullable=False, index=True)
    block_timestamp = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), nullable=False, default='CONFIRMED', server_default=text("'CONFIRMED'"))
    meta_data = Column(JSONB, default=dict, nullable=True, server_default=text("'{}'::jsonb"))

    initiator_user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=True, index=True)
    receiver_user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=True, index=True)

    goodwill_action = relationship("GoodwillAction", backref="ledger_entry", uselist=False,
                                   primaryjoin="LedgerEntry.goodwill_action_id == GoodwillAction.id")
    initiator_user = relationship("UserAccount", foreign_keys=[initiator_user_id], backref="initiated_ledger_entries")
    receiver_user = relationship("UserAccount", foreign_keys=[receiver_user_id], backref="received_ledger_entries")

    def __repr__(self) -> str:
        return f"<LedgerEntry id={self.id} tx_hash={self.blockchain_tx_hash[:8]}... type={self.transaction_type}>"

class ChainBlock(BaseModel, TimestampMixin):
    __tablename__ = 'chain_blocks'

    id = db.Column(db.Integer, primary_key=True)
    block_hash = db.Column(db.String(128), nullable=False, unique=True)
    previous_hash = db.Column(db.String(128), nullable=True)
    data = db.Column(db.JSON, nullable=False)
    height = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f"<ChainBlock {self.height} - {self.block_hash}>"

    def to_dict(self):
        return {
            "id": self.id,
            "block_hash": self.block_hash,
            "previous_hash": self.previous_hash,
            "data": self.data,
            "height": self.height,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

class Proposal(BaseModel, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'proposals'
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'VOTING', 'PASSED', 'FAILED', 'EXECUTED')",
            name='chk_proposal_status_valid'
        ),
    )

    proposer_user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(50), default='DRAFT', nullable=False, server_default=text("'DRAFT'"))
    vote_start_time = Column(DateTime(timezone=True), nullable=True)
    vote_end_time = Column(DateTime(timezone=True), nullable=True)
    required_quorum = Column(Numeric(5, 2), default=0, nullable=False, server_default=text('0'))  # 0.0 - 1.0
    proposal_type = Column(String(100), nullable=False)
    details = Column(JSONB, default=dict, nullable=True, server_default=text("'{}'::jsonb"))

    votes = relationship("Vote", back_populates="proposal", lazy='dynamic',
                         primaryjoin="Proposal.id == Vote.proposal_id")
    proposer = relationship("UserAccount", back_populates="proposals")

    def __repr__(self):
        return f"<Proposal id={self.id} title={self.title} status={self.status}>"


class Vote(BaseModel, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'votes'

    voter_user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    proposal_id = Column(PG_UUID(as_uuid=True), ForeignKey('proposals.id'), nullable=False, index=True)
    vote_value = Column(String(10), nullable=False)  # 'YES', 'NO', 'ABSTAIN'
    rationale = Column(Text, nullable=True)

    voter = relationship("UserAccount", back_populates="votes")
    proposal = relationship("Proposal", back_populates="votes")

    def __repr__(self):
        return f"<Vote id={self.id} voter={self.voter_user_id} proposal={self.proposal_id} value={self.vote_value}>"


class CouncilMember(BaseModel, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'council_members'

    user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, unique=True)
    role = Column(String(100), nullable=False)  # e.g., Chair, Treasurer
    start_date = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    end_date = Column(DateTime(timezone=True), nullable=True)

    user = relationship("UserAccount", back_populates="council_member_profile")

    def __repr__(self):
        return f"<CouncilMember user_id={self.user_id} role={self.role}>"

# Add any additional models as needed

