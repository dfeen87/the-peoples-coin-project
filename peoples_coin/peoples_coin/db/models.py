# peoples_coin/peoples_coin/db/models.py

from datetime import datetime, timezone
from typing import Dict, Any
from sqlalchemy import Index
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.dialects.sqlite import JSON
from decimal import Decimal

from .db import db

def utcnow():
    """Returns the current time in UTC timezone."""
    return datetime.now(timezone.utc)

class DataEntry(db.Model):
    """
    SQLAlchemy model for data entries with processing status and timestamps.
    Includes soft delete support.
    """
    __tablename__ = 'data_entries'
    __table_args__ = (
        db.Index('idx_processed_created_at', 'processed', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    value = db.Column(db.String(255), nullable=True)
    processed = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the object to a dictionary."""
        return {
            'id': self.id,
            'value': self.value,
            'processed': self.processed,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None,
        }

    def __repr__(self):
        return f"<DataEntry id={self.id} processed={self.processed}>"

class GoodwillAction(db.Model):
    """
    Represents a verified goodwill action, serving as the input for the Metabolic System.
    Soft delete enabled.
    """
    __tablename__ = 'goodwill_actions'
    __table_args__ = (
        db.Index('idx_goodwill_status', 'status'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), nullable=False, index=True)
    action_type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    contextual_data = db.Column(JSON, default=dict)
    raw_goodwill_score = db.Column(db.Integer, default=0, nullable=False)
    resonance_score = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(50), default='pending', nullable=False)
    processed_at = db.Column(db.DateTime, nullable=True)
    minted_token_id = db.Column(db.String(255), nullable=True, unique=True)
    deleted_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action_type": self.action_type,
            "description": self.description,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "contextual_data": self.contextual_data,
            "raw_goodwill_score": self.raw_goodwill_score,
            "resonance_score": self.resonance_score,
            "status": self.status,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "minted_token_id": self.minted_token_id,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }

    def __repr__(self):
        return f"<GoodwillAction id={self.id} status={self.status} user_id={self.user_id}>"

class EventLog(db.Model):
    """Logs significant events within the system."""
    __tablename__ = 'event_logs'
    __table_args__ = (
        db.Index('idx_event_type_timestamp', 'event_type', 'timestamp'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_type = db.Column(db.String(64), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "event_type": self.event_type,
            "message": self.message,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }

    def __repr__(self):
        return f"<EventLog id={self.id} event_type={self.event_type}>"

class UserAccount(db.Model):
    """
    Represents a user's account, holding their balance in 'Loves'.
    Soft delete enabled.
    """
    __tablename__ = 'user_accounts'

    user_id = db.Column(db.String(255), primary_key=True, nullable=False)
    balance = db.Column(db.Numeric(precision=18, scale=4), default=Decimal('0.0'), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "balance": str(self.balance),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }

    def __repr__(self):
        return f"<UserAccount user_id={self.user_id} balance={self.balance}>"

# ===== NEW MODELS FOR CONSENSUS SYSTEM =====

class ConsensusNode(db.Model):
    """
    Represents a registered node in the consensus network.
    This replaces the in-memory `self.nodes` dictionary.
    """
    __tablename__ = 'consensus_nodes'

    id = db.Column(db.String(255), primary_key=True)
    address = db.Column(db.String(255), unique=True, nullable=False)
    registered_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "address": self.address,
            "registered_at": self.registered_at.isoformat() if self.registered_at else None
        }

    def __repr__(self):
        return f"<ConsensusNode id={self.id} address={self.address}>"

class ChainBlock(db.Model):
    """
    Represents a single block in the blockchain, stored in the database.
    This replaces the `chain.json` file.
    """
    __tablename__ = 'chain_blocks'

    # The block's index is the primary key
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.Float, nullable=False)  # Consider changing to DateTime if preferred
    transactions = db.Column(JSON, nullable=False)
    previous_hash = db.Column(db.String(64), nullable=False)
    nonce = db.Column(db.Integer, default=0, nullable=False)
    hash = db.Column(db.String(64), unique=True, nullable=False, index=True)

    def to_dict(self):
        return {
            "index": self.id,
            "timestamp": self.timestamp,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash
        }

    def __repr__(self):
        return f"<ChainBlock index={self.id} hash={self.hash[:8]}...>"


