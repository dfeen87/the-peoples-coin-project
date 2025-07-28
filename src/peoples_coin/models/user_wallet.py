import uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import Column, String, Boolean, ForeignKey, LargeBinary, DateTime, func
from sqlalchemy.orm import relationship
from peoples_coin.extensions import db

class UserWallet(db.Model):
    __tablename__ = 'user_wallets'

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey('user_accounts.id', ondelete='CASCADE'), nullable=False, index=True) # FIX WAS HERE
    public_address = Column(String(42), unique=True, nullable=False)
    blockchain_network = Column(String(50), nullable=False, default='Ethereum Mainnet')
    is_primary = Column(Boolean, nullable=False, default=False)
    encrypted_data = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    user = relationship("UserAccount", back_populates="user_wallets")
