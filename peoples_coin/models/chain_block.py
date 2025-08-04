# src/peoples_coin/models/chain_block.py

import uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy import Column, Integer, LargeBinary, String, DateTime, Numeric, func, CheckConstraint, ForeignKey
from peoples_coin.extensions import db
from peoples_coin.db_types import JSONType, UUIDType, EnumType
from peoples_coin.db_types import JSONB

class ChainBlock(db.Model):
    __tablename__ = "chain_blocks"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Matches schema
    height = Column(Integer, nullable=False, unique=True, index=True)

    # 32-byte hashes (SHA-256)
    previous_hash = Column(LargeBinary(32), ForeignKey("chain_blocks.current_hash"), nullable=True)
    current_hash = Column(LargeBinary(32), nullable=False, unique=True)

    # Metadata
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    miner = Column(String(64), nullable=True)

    # Summary fields
    tx_count = Column(Integer, nullable=False, default=0)
    goodwill_actions_count = Column(Integer, nullable=False, default=0)
    proposals_count = Column(Integer, nullable=False, default=0)
    ledger_total_amount = Column(Numeric(20, 8), nullable=False, default=0.0)

    # JSON summary
    block_summary = Column(JSONB, nullable=True, default=dict)

    # Constraints from schema
    __table_args__ = (
        CheckConstraint("octet_length(current_hash) = 32", name="check_current_hash_len"),
        CheckConstraint("previous_hash IS NULL OR octet_length(previous_hash) = 32", name="check_previous_hash_len"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "height": self.height,
            "previous_hash": self.previous_hash.hex() if self.previous_hash else None,
            "current_hash": self.current_hash.hex(),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "miner": self.miner,
            "tx_count": self.tx_count,
            "goodwill_actions_count": self.goodwill_actions_count,
            "proposals_count": self.proposals_count,
            "ledger_total_amount": float(self.ledger_total_amount),
            "block_summary": self.block_summary or {},
        }