# peoples_coin/models/notification.py

import uuid
from sqlalchemy import (
    Column, String, Text, DateTime, func, ForeignKey, Boolean
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ENUM
from peoples_coin.extensions import db

class Notification(db.Model):
    __tablename__ = "notifications"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    
    type = Column(
        ENUM('PROPOSAL_UPDATE', 'VOTE_RESULT', 'NEW_COMMENT', 'GOODWILL_VERIFIED', 'GOODWILL_REJECTED', 'FUNDS_RECEIVED', 'MENTION', 'BOUNTY_COMPLETED', name='notification_type', create_type=False),
        nullable=False
    )
    
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    link_url = Column(Text, nullable=True)
    is_read = Column(Boolean, nullable=False, default=False)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationship to link back to the UserAccount model
    recipient = relationship("UserAccount", back_populates="notifications")

    def to_dict(self):
        """Serializes the Notification object to a dictionary."""
        return {
            "id": str(self.id),
            "recipient_user_id": str(self.recipient_user_id),
            "type": self.type,
            "title": self.title,
            "body": self.body,
            "link_url": self.link_url,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
