import uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ENUM
from sqlalchemy import (
    Column, String, Integer, Text, DateTime, JSON, func, ForeignKey
)
from peoples_coin.extensions import db


class GoodwillLedger(db.Model):
    __tablename__ = "goodwill_ledger"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    transaction_type = Column(
        ENUM('EARNED_ACTION', 'SPENT_ON_FEATURE', 'ADMIN_ADJUSTMENT', 'REWARD', 'BOUNTY_PAYOUT', name='goodwill_transaction_type'),
        nullable=False
    )
    amount = Column(Integer, nullable=False)
    balance_after_transaction = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)
    related_goodwill_action_id = Column(PG_UUID(as_uuid=True), ForeignKey("goodwill_actions.id", ondelete="SET NULL"), nullable=True)
    meta_data = Column(db.JSON().with_variant(db.JSONB, "postgresql"), nullable=True, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("UserAccount", backref="goodwill_ledger")
    related_goodwill_action = relationship("GoodwillAction", backref="ledger_entries")

    def to_dict(self):
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

