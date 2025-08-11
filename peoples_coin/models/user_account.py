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
    username = Column(String(64), nullable=True, unique=True)
    password_hash = Column(String(128), nullable=True)
    balance = Column(Numeric(20, 4), nullable=False, default=0.0)
    goodwill_coins = Column(Integer, nullable=False, default=0)
    bio = Column(Text, nullable=True)
    profile_image_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # --- ADDED: All relationships to other models ---

    # Core
    user_wallets = relationship("UserWallet", back_populates="user_account", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="user_account", cascade="all, delete-orphan")
    token_assets = relationship("UserTokenAsset", back_populates="user_account", cascade="all, delete-orphan")
    
    # Goodwill & Ledgers
    goodwill_actions = relationship("GoodwillAction", back_populates="performer", cascade="all, delete-orphan")
    goodwill_ledger_entries = relationship("GoodwillLedger", back_populates="user", cascade="all, delete-orphan")
    initiated_ledger_entries = relationship("LedgerEntry", foreign_keys="LedgerEntry.initiator_user_id", back_populates="initiator_user")
    received_ledger_entries = relationship("LedgerEntry", foreign_keys="LedgerEntry.receiver_user_id", back_populates="receiver_user")

    # Governance
    proposals = relationship("Proposal", back_populates="proposer", cascade="all, delete-orphan")
    votes = relationship("Vote", back_populates="voter", cascade="all, delete-orphan")
    council_membership = relationship("CouncilMember", back_populates="user_account", uselist=False, cascade="all, delete-orphan")
    created_bounties = relationship("Bounty", back_populates="creator", cascade="all, delete-orphan")

    # Social
    action_loves = relationship("ActionLove", back_populates="user_account", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="author", cascade="all, delete-orphan")
    # `followers` relationship is more complex and defined in the Follower model

    # System & Security
    notifications = relationship("Notification", back_populates="recipient", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="actor", cascade="all, delete-orphan")
    submitted_reports = relationship("ContentReport", foreign_keys="ContentReport.reporter_user_id", back_populates="reporter", cascade="all, delete-orphan")
    reviewed_reports = relationship("ContentReport", foreign_keys="ContentReport.reviewer_user_id", back_populates="reviewer")
    controller_actions = relationship("ControllerAction", back_populates="user_account", cascade="all, delete-orphan")

    def to_dict(self, include_wallets: bool = True):
        """Serializes the UserAccount object to a dictionary."""
        user_data = {
            "id": str(self.id),
            "firebase_uid": self.firebase_uid,
            "email": self.email,
            "username": self.username,
            "balance": str(self.balance),
            "goodwill_coins": self.goodwill_coins,
            "bio": self.bio,
            "profile_image_url": self.profile_image_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
        # The relationship property name is now `user_wallets`
        if include_wallets and self.user_wallets:
            user_data["wallets"] = [wallet.to_dict() for wallet in self.user_wallets]
        return user_data
