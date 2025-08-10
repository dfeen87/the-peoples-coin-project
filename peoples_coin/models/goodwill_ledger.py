# peoples_coin/models/goodwill_ledger.py

import uuid
from sqlalchemy import Column, String, Integer, Text, DateTime, func, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ENUM, JSONB
from peoples_coin.extensions import db

class GoodwillLedger(db.Model):
    __tablename__ = "goodwill_ledger"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    
    # This correctly uses the ENUM type defined in your schema
    transaction_type = Column(
        ENUM('EARNED_ACTION', 'SPENT_ON_FEATURE', 'ADMIN_ADJUSTMENT', 'REWARD', 'BOUNTY_PAYOUT', name='goodwill_transaction_type', create_type=False),
        nullable=False
    )
    
    amount = Column(Integer, nullable=False)
    balance_after_transaction = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)
    related_goodwill_action_id = Column(PG_UUID(as_uuid=True), ForeignKey("goodwill_actions.id", ondelete="SET NULL"), nullable=True)
    
    # --- CHANGE: Use the standard SQLAlchemy JSONB type ---
    meta_data = Column(JSONB, nullable=True, server_default=func.text("'{}'::jsonb"))
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # --- CHANGE: Relationships updated for consistency ---
    user = relationship("UserAccount", back_populates="goodwill_ledger_entries")
    related_goodwill_action = relationship("GoodwillAction", back_populates="goodwill_ledger_entries")

    def to_dict(self):
        """Serializes the GoodwillLedger object to a dictionary."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "transaction_type": self.transaction_type,
            "amount": self.amount,
            "balance_after_transaction": self.balance_after_transaction,
            "description": self.description,
            "related_goodwill_action_id": str(self.related_goodwill_action_id) if self.related_goodwill_action_id else None,
            "meta_data": self.meta_data,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
