# peoples_coin/models/user_token_asset.py

import uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import (
    Column, String, Text, DateTime, Numeric, func, ForeignKey
)
from sqlalchemy.orm import relationship
from peoples_coin.extensions import db

class UserTokenAsset(db.Model):
    __tablename__ = "user_token_assets"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_wallet_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_wallets.id", ondelete="CASCADE"), nullable=False, index=True)
    
    token_symbol = Column(String(10), nullable=False)
    balance = Column(Numeric(20, 8), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # --- Relationships ---
    user_account = relationship("UserAccount", back_populates="token_assets")
    user_wallet = relationship("UserWallet", back_populates="token_assets")

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "user_wallet_id": str(self.user_wallet_id),
            "token_symbol": self.token_symbol,
            "balance": str(self.balance),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
