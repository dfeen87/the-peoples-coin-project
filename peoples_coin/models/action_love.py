# peoples_coin/models/action_love.py

import uuid
from sqlalchemy import (
    Column, DateTime, func, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from peoples_coin.extensions import db

class ActionLove(db.Model):
    __tablename__ = "action_loves"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    goodwill_action_id = Column(PG_UUID(as_uuid=True), ForeignKey("goodwill_actions.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # --- Relationships ---
    user_account = relationship("UserAccount", back_populates="action_loves")
    goodwill_action = relationship("GoodwillAction", back_populates="loves")

    # --- Constraints ---
    # Ensures a user can only "love" an action once
    __table_args__ = (
        UniqueConstraint('user_id', 'goodwill_action_id', name='unique_user_action_love'),
    )

    def to_dict(self):
        """Serializes the ActionLove object to a dictionary."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "goodwill_action_id": str(self.goodwill_action_id),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
