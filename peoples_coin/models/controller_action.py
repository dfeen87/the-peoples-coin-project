# peoples_coin/models/controller_action.py

from sqlalchemy import (
    Column, Integer, DateTime, func, ForeignKey
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from peoples_coin.extensions import db

class ControllerAction(db.Model):
    __tablename__ = "controller_actions"

    # Note: This table uses a standard auto-incrementing integer for its primary key.
    id = Column(Integer, primary_key=True)
    
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True)
    recommendations = Column(JSONB, nullable=True)
    actions_taken = Column(JSONB, nullable=True)

    # Relationship to link back to the UserAccount model
    user_account = relationship("UserAccount", back_populates="controller_actions")

    def to_dict(self):
        """Serializes the ControllerAction object to a dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "recommendations": self.recommendations,
            "actions_taken": self.actions_taken,
        }
