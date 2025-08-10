# peoples_coin/models/follower.py

from sqlalchemy import (
    Column, DateTime, func, ForeignKey, PrimaryKeyConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from peoples_coin.extensions import db

class Follower(db.Model):
    __tablename__ = "followers"

    follower_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    followed_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # --- Define a composite primary key ---
    __table_args__ = (
        PrimaryKeyConstraint('follower_user_id', 'followed_user_id'),
    )

    # --- Relationships ---
    # Note: These relationships are defined on the UserAccount model
    # to complete the many-to-many link.

    def to_dict(self):
        """Serializes the Follower object to a dictionary."""
        return {
            "follower_user_id": str(self.follower_user_id),
            "followed_user_id": str(self.followed_user_id),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
