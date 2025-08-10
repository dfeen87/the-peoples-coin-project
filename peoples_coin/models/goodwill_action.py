# peoples_coin/models/goodwill_action.py

import uuid
from sqlalchemy import (
    Column, String, Integer, Text, DateTime,
    ForeignKey, func, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ENUM, JSONB
from peoples_coin.extensions import db

class GoodwillAction(db.Model):
    __tablename__ = "goodwill_actions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    performer_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True)
    action_type = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    contextual_data = Column(JSONB, nullable=False, server_default=func.text("'{}'::jsonb"))
    loves_value = Column(Integer, nullable=False, default=0)
    
    status = Column(
        ENUM('PENDING_VERIFICATION', 'VERIFIED', 'REJECTED', name='goodwill_status', create_type=False),
        nullable=False,
        server_default='PENDING_VERIFICATION'
    )
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # --- ADDED: All relationships to other models ---
    performer = relationship("UserAccount", back_populates="goodwill_actions")
    ledger_entry = relationship("LedgerEntry", back_populates="goodwill_action", uselist=False)
    goodwill_ledger_entries = relationship("GoodwillLedger", back_populates="related_goodwill_action")
    loves = relationship("ActionLove", back_populates="goodwill_action", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="goodwill_action", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary="goodwill_action_tags", back_populates="goodwill_actions")

    __table_args__ = (
        CheckConstraint('loves_value >= 0', name='check_loves_value_nonnegative'),
    )

    def to_dict(self):
        """Serializes the GoodwillAction object to a dictionary."""
        return {
            "id": str(self.id),
            "performer_user_id": str(self.performer_user_id) if self.performer_user_id else None,
            "action_type": self.action_type,
            "description": self.description,
            "contextual_data": self.contextual_data,
            "loves_value": self.loves_value,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
