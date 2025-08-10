# peoples_coin/models/chain_block.py

import uuid
from sqlalchemy import Column, Integer, LargeBinary, DateTime, func, CheckConstraint, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from peoples_coin.extensions import db

class ChainBlock(db.Model):
    __tablename__ = "chain_blocks"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    height = Column(Integer, nullable=False, unique=True, index=True)
    
    # --- CHANGE: Using LargeBinary for BYTEA type from your schema ---
    previous_hash = Column(LargeBinary(32), nullable=True)
    current_hash = Column(LargeBinary(32), nullable=False, unique=True)

    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    # --- CHANGE: Removed columns not present in the final schema ---
    # The following were removed for consistency:
    # miner, goodwill_actions_count, proposals_count, ledger_total_amount, block_summary
    tx_count = Column(Integer, nullable=False, default=0)

    # --- This correctly reflects the check constraints in your final schema ---
    __table_args__ = (
        CheckConstraint('octet_length(current_hash) = 32'),
        CheckConstraint('previous_hash IS NULL OR octet_length(previous_hash) = 32'),
    )

    def to_dict(self):
        """Serializes the ChainBlock object to a dictionary."""
        return {
            "id": str(self.id),
            "height": self.height,
            "previous_hash": self.previous_hash.hex() if self.previous_hash else None,
            "current_hash": self.current_hash.hex() if self.current_hash else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "tx_count": self.tx_count,
        }
