# peoples_coin/models/api_key.py

import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from peoples_coin.extensions import db

class ApiKey(db.Model):
    __tablename__ = "api_keys"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(64), unique=True, nullable=False)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    # --- CHANGE: Add the deleted_at column for soft deletes ---
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    user_account = relationship("UserAccount", back_populates="api_keys")
