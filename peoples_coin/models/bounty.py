# peoples_coin/models/bounty.py

import uuid
from sqlalchemy import (
    Column, String, Text, DateTime, Numeric, func, ForeignKey
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ENUM
from peoples_coin.extensions import db

class Bounty(db.Model):
    __tablename__ = "bounties"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True)
    
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    
    status = Column(
        ENUM('DRAFT', 'ACTIVE', 'CLOSED', 'REJECTED', name='bounty_status', create_type=False),
        nullable=False,
        server_default='ACTIVE'
    )
    
    reward_amount = Column(Numeric(20, 8), nullable=False)
    reward_token_symbol = Column(String(10), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    creator = relationship("UserAccount", back_populates="created_bounties")

    def to_dict(self):
        """Serializes the Bounty object to a dictionary."""
        return {
            "id": str(self.id),
            "created_by_user_id": str(self.created_by_user_id) if self.created_by_user_id else None,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "reward_amount": str(self.reward_amount),
            "reward_token_symbol": self.reward_token_symbol,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
