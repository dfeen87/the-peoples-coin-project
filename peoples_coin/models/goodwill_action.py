# src/peoples_coin/models/goodwill_action.py

import uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import (
    Column, String, Integer, Text, DateTime, Float,
    ForeignKey, func, JSON
)
from sqlalchemy.orm import relationship
from peoples_coin.extensions import db


class GoodwillAction(db.Model):
    __tablename__ = "goodwill_actions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    performer_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True)
    action_type = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    contextual_data = Column(JSON, nullable=False, server_default="{}")
    loves_value = Column(Integer, nullable=False, default=0)
    resonance_score = Column(Float, nullable=True)
    status = Column(String(50), nullable=False, default="PENDING_VERIFICATION")
    processed_at = Column(DateTime(timezone=True), nullable=True)
    blockchain_tx_hash = Column(String(66), unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    performer = relationship("UserAccount", backref="goodwill_actions")

    def to_dict(self):
        return {
            "id": str(self.id),
            "performer_user_id": str(self.performer_user_id) if self.performer_user_id else None,
            "action_type": self.action_type,
            "description": self.description,
            "contextual_data": self.contextual_data,
            "loves_value": self.loves_value,
            "resonance_score": self.resonance_score,
            "status": self.status,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "blockchain_tx_hash": self.blockchain_tx_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

