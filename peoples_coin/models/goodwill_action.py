import uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ENUM, JSONB
from sqlalchemy import (
    Column, String, Integer, Text, DateTime, Float,
    ForeignKey, func, CheckConstraint, text, JSON
)
from sqlalchemy.orm import relationship
from peoples_coin.extensions import db
from peoples_coin.db_types import JSONType, UUIDType, EnumType
from peoples_coin.db_types import JSONB


class GoodwillAction(db.Model):
    __tablename__ = "goodwill_actions"

    __table_args__ = (
        CheckConstraint('loves_value >= 0', name='check_loves_value_nonnegative'),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    performer_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True)
    action_type = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    contextual_data = Column(
        JSON().with_variant(JSONB, "postgresql"), 
        nullable=False, 
        server_default=text("'{}'::jsonb")
    )
    loves_value = Column(Integer, nullable=False, default=0)
    resonance_score = Column(Float, nullable=True)
    status = Column(
        EnumType('PENDING_VERIFICATION', 'VERIFIED', 'REJECTED', name='goodwill_status'),
        nullable=False,
        server_default='PENDING_VERIFICATION'
    )
    processed_at = Column(DateTime(timezone=True), nullable=True)
    blockchain_tx_hash = Column(String(66), unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

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