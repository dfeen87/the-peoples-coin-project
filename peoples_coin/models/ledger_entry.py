import uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import (
    Column, String, Numeric, BigInteger, DateTime, ForeignKey, JSON, func
)
from sqlalchemy.orm import relationship
from peoples_coin.extensions import db


class LedgerEntry(db.Model):
    __tablename__ = "ledger_entries"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    blockchain_tx_hash = Column(String(66), unique=True, nullable=False)
    goodwill_action_id = Column(PG_UUID(as_uuid=True), ForeignKey("goodwill_actions.id", ondelete="SET NULL"), unique=True, nullable=True)
    transaction_type = Column(String(50), nullable=False)
    amount = Column(Numeric(20, 8), nullable=False)
    token_symbol = Column(String(10), nullable=False)
    sender_address = Column(String(42), nullable=False)
    receiver_address = Column(String(42), nullable=False)
    block_number = Column(BigInteger, nullable=False)
    block_timestamp = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), nullable=False, default='CONFIRMED')
    meta_data = Column(db.JSON().with_variant(db.JSONB, "postgresql"), nullable=True, server_default=text("'{}'::jsonb"))
    initiator_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id"), nullable=True)
    receiver_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    goodwill_action = relationship("GoodwillAction", backref="ledger_entry", uselist=False)
    initiator_user = relationship("UserAccount", foreign_keys=[initiator_user_id])
    receiver_user = relationship("UserAccount", foreign_keys=[receiver_user_id])

    def to_dict(self):
        return {
            "id": str(self.id),
            "blockchain_tx_hash": self.blockchain_tx_hash,
            "goodwill_action_id": str(self.goodwill_action_id) if self.goodwill_action_id else None,
            "transaction_type": self.transaction_type,
            "amount": float(self.amount),
            "token_symbol": self.token_symbol,
            "sender_address": self.sender_address,
            "receiver_address": self.receiver_address,
            "block_number": self.block_number,
            "block_timestamp": self.block_timestamp.isoformat() if self.block_timestamp else None,
            "status": self.status,
            "meta_data": self.meta_data,
            "initiator_user_id": str(self.initiator_user_id) if self.initiator_user_id else None,
            "receiver_user_id": str(self.receiver_user_id) if self.receiver_user_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

