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
    
    # --- FIXED: Added ForeignKey constraint to link blocks in the chain ---
    previous_hash = Column(LargeBinary(32), ForeignKey("chain_blocks.current_hash"), nullable=True)
    current_hash = Column(LargeBinary(32), nullable=False, unique=True)

    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    tx_count = Column(Integer, nullable=False, default=0)

    # Note: `__table_args__` is correct as-is.

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
