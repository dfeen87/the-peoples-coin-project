import uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import Column, String, Integer, Text, DateTime, Numeric, func
from sqlalchemy.orm import relationship
from peoples_coin.extensions import db

class UserAccount(db.Model):
    __tablename__ = 'user_accounts'

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firebase_uid = Column(String(128), unique=True, nullable=False)
    email = Column(String(256), unique=True, nullable=True)
    username = Column(String(64), nullable=True)
    balance = Column(Numeric(20, 4), nullable=False, default=0.0)
    goodwill_coins = Column(Integer, nullable=False, default=0)
    bio = Column(Text, nullable=True)
    profile_image_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    user_wallets = relationship("UserWallet", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")

    def to_dict(self, include_wallets: bool = True):
        user_data = {
            "id": str(self.id),
            "firebase_uid": self.firebase_uid,
            "email": self.email,
            "username": self.username,
            "balance": float(self.balance),
            "goodwill_coins": self.goodwill_coins,
            "bio": self.bio,
            "profile_image_url": self.profile_image_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
        if include_wallets:
            user_data["wallets"] = [wallet.to_dict() for wallet in self.user_wallets]
        return user_data

