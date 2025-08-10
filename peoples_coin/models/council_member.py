# peoples_coin/models/council_member.py

import uuid
from sqlalchemy import (
    Column, String, DateTime, func, ForeignKey, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from peoples_coin.extensions import db

class CouncilMember(db.Model):
    __tablename__ = "council_members"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # A user can only hold one council seat at a time.
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    role = Column(String(100), nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    end_date = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationship to link back to the UserAccount model
    user_account = relationship("UserAccount", back_populates="council_membership")

    # Ensures the end_date is after the start_date if it exists
    __table_args__ = (
        CheckConstraint('end_date IS NULL OR end_date > start_date', name='check_end_date_after_start_date'),
    )

    def to_dict(self):
        """Serializes the CouncilMember object to a dictionary."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "role": self.role,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
