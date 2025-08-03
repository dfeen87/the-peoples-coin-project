# src/peoples_coin/models/chain_block.py

import uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import Column, Integer, String, DateTime, func
from peoples_coin.extensions import db

class ChainBlock(db.Model):
    __tablename__ = "chain_blocks"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    height = Column(Integer, nullable=False, unique=True, index=True)  # Block number
    previous_hash = Column(String(66), nullable=True)  # Hash of previous block, e.g. "0x..."
    current_hash = Column(String(66), nullable=False, unique=True)  # Current block's hash
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    data = Column(String, nullable=True)  # Could be JSON string or summary data
    miner = Column(String(64), nullable=True)  # Optional: who created/mined block

    def __repr__(self):
        return f"<ChainBlock height={self.height} hash={self.current_hash[:10]}...>"

