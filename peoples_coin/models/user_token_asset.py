# peoples_coin/models/user_token_asset.py

import uuid
from sqlalchemy import (
    Column, String, Numeric, DateTime, func, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from peoples_coin.extensions import db

class UserTokenAsset(db.Model):
    __tablename__ = "user_token_assets"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_account_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    wallet_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_wallets.id", ondelete="CASCADE"), nullable=False)
    
    blockchain_network = Column(String(50), nullable=False)
    contract_address = Column(String(42), nullable=False)
    token_id = Column(Numeric(78, 0), nullable=False) # Large enough for uint256
    
    metadata = Column(JSONB, nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships to link back to the UserAccount and UserWallet models
    user_account = relationship("UserAccount", back_populates="token_assets")
    wallet = relationship("UserWallet", back_populates="token_assets")

    # Ensures that each token is only listed once in the database
    __table_args__ = (
        UniqueConstraint('blockchain_network', 'contract_address', 'token_id', name='unique_token_instance'),
    )

    def to_dict(self):
        """Serializes the UserTokenAsset object to a dictionary."""
        return {
            "id": str(self.id),
            "user_account_id": str(self.user_account_id),
            "wallet_id": str(self.wallet_id),
            "blockchain_network": self.blockchain_network,
            "contract_address": self.contract_address,
            "token_id": str(self.token_id),
            "metadata": self.metadata,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
