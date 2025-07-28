from datetime import datetime, timezone
import uuid
from typing import Dict, Any

from sqlalchemy.orm import Query, relationship
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Integer, Float, Text,
    Numeric, CheckConstraint, Index, BigInteger, text
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from peoples_coin.extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class SoftDeleteQuery(Query):
    _with_deleted = False

    def with_deleted(self):
        self._with_deleted = True
        return self

    def __iter__(self):
        if self._with_deleted or not hasattr(self._entity_from_pre_ent_zero().class_, "deleted_at"):
            return super().__iter__()
        return super().filter(self._entity_from_pre_ent_zero().class_.deleted_at.is_(None)).__iter__()

class BaseModel(db.Model):
    __abstract__ = True
    query_class = SoftDeleteQuery
    query: SoftDeleteQuery

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.id}>"

class SoftDeleteMixin:
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

class UserAccount(BaseModel, SoftDeleteMixin):
    __tablename__ = 'users'

    firebase_uid = Column(String(128), unique=True, nullable=False, index=True)
    email = Column(String(256), unique=True, nullable=True, index=True)
    username = Column(String(64), nullable=True, index=True)
    balance = Column(Numeric(20, 8), default=0, nullable=False)
    goodwill_coins = Column(Integer, nullable=False, default=0)
    bio = Column(Text, nullable=True)
    profile_image_url = Column(Text, nullable=True)
    is_premium = Column(Boolean, default=False, nullable=False)

    # Relationships
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    goodwill_actions = relationship("GoodwillAction", back_populates="performer", lazy='dynamic')
    # user_wallets relationship remains here, but make sure to import UserWallet from models/user_wallet.py in your package
    user_wallets = relationship("UserWallet", back_populates="user", cascade="all, delete-orphan")
    proposals = relationship("Proposal", back_populates="proposer", lazy='dynamic')
    votes = relationship("Vote", back_populates="voter", lazy='dynamic')
    council_member_profile = relationship("CouncilMember", back_populates="user", uselist=False)

class ApiKey(BaseModel):
    __tablename__ = 'api_keys'
    key = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    user = relationship("UserAccount", back_populates="api_keys")

class GoodwillAction(BaseModel, SoftDeleteMixin):
    __tablename__ = 'goodwill_actions'
    performer_user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=True, index=True)
    action_type = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    contextual_data = Column(JSONB, default=dict, nullable=False)
    loves_value = Column(Integer, default=0, nullable=False)
    resonance_score = Column(Float, nullable=True)
    status = Column(String(50), default='PENDING_VERIFICATION', nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    blockchain_tx_hash = Column(String(66), nullable=True, unique=True)
    performer = relationship("UserAccount", back_populates="goodwill_actions")

class LedgerEntry(BaseModel):
    __tablename__ = 'ledger_entries'
    blockchain_tx_hash = Column(String(66), unique=True, nullable=False, index=True)
    goodwill_action_id = Column(PG_UUID(as_uuid=True), ForeignKey('goodwill_actions.id'), nullable=True, unique=True)
    transaction_type = Column(String(50), nullable=False)
    amount = Column(Numeric(20, 8), nullable=False)
    sender_address = Column(String(42), nullable=False)
    receiver_address = Column(String(42), nullable=False)
    block_number = Column(BigInteger, nullable=False)
    block_timestamp = Column(DateTime(timezone=True), nullable=False)

class ChainBlock(db.Model):
    __tablename__ = 'chain_blocks'
    id = Column(Integer, primary_key=True)
    block_hash = Column(String(128), nullable=False, unique=True)
    previous_hash = Column(String(128), nullable=True)
    data = Column(JSONB, nullable=False)
    height = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    def to_dict(self):
        return {
            "height": self.height,
            "block_hash": self.block_hash,
            "previous_hash": self.previous_hash,
            "data": self.data,
            "created_at": self.created_at.isoformat()
        }

class Proposal(BaseModel, SoftDeleteMixin):
    __tablename__ = 'proposals'
    proposer_user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(50), default='DRAFT', nullable=False)
    vote_start_time = Column(DateTime(timezone=True), nullable=True)
    vote_end_time = Column(DateTime(timezone=True), nullable=True)
    proposer = relationship("UserAccount", back_populates="proposals")
    votes = relationship("Vote", back_populates="proposal", lazy='dynamic', cascade="all, delete-orphan")

class Vote(BaseModel, SoftDeleteMixin):
    __tablename__ = 'votes'
    voter_user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    proposal_id = Column(PG_UUID(as_uuid=True), ForeignKey('proposals.id'), nullable=False, index=True)
    vote_value = Column(String(10), nullable=False) # 'YES', 'NO', 'ABSTAIN'
    voter = relationship("UserAccount", back_populates="votes")
    proposal = relationship("Proposal", back_populates="votes")

class CouncilMember(BaseModel, SoftDeleteMixin):
    __tablename__ = 'council_members'
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, unique=True)
    role = Column(String(100), nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    end_date = Column(DateTime(timezone=True), nullable=True)
    user = relationship("UserAccount", back_populates="council_member_profile")

