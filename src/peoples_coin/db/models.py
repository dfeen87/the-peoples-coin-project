from datetime import datetime, timezone
from typing import Dict, Any
from decimal import Decimal

# Correctly import the db instance from your dedicated database file.
from .db import db

# Helper function to ensure all default timestamps are timezone-aware (UTC).
def utcnow():
    """Returns the current time in the UTC timezone."""
    return datetime.now(timezone.utc)


# ==============================================================================
# 1. Mixin Classes for Code Reusability
# ==============================================================================

class TimestampMixin:
    """
    Mixin class to add created_at and updated_at timestamp columns to a model.
    This ensures consistency and reduces boilerplate code.
    """
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

class SoftDeleteMixin:
    """Mixin class to add a soft-delete timestamp column."""
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)


# ==============================================================================
# 2. Core Application Models
# ==============================================================================

class DataEntry(db.Model, TimestampMixin, SoftDeleteMixin):
    """
    SQLAlchemy model for data entries with processing status and timestamps.
    """
    __tablename__ = 'data_entries'
    __table_args__ = (
        db.Index('idx_processed_created_at', 'processed', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # Use db.Text for potentially long JSON strings instead of db.String(255).
    value = db.Column(db.Text, nullable=True)
    processed = db.Column(db.Boolean, default=False, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the object to a dictionary."""
        return {
            'id': self.id,
            'value': self.value,
            'processed': self.processed,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None,
        }

    def __repr__(self):
        return f"<DataEntry id={self.id} processed={self.processed}>"

class GoodwillAction(db.Model, SoftDeleteMixin):
    """
    Represents a verified goodwill action, serving as the input for the Metabolic System.
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
    # Use the generic db.JSON type for portability across different database systems.
    contextual_data = db.Column(db.JSON, default=dict)
    raw_goodwill_score = db.Column(db.Integer, default=0, nullable=False)
    resonance_score = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(50), default='pending', nullable=False)
    processed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    minted_token_id = db.Column(db.String(255), nullable=True, unique=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action_type": self.action_type,
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
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
    timestamp = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "event_type": self.event_type,
            "message": self.message,
            "timestamp": self.timestamp.isoformat()
        }

    def __repr__(self):
        return f"<EventLog id={self.id} event_type={self.event_type}>"

class UserAccount(db.Model, TimestampMixin, SoftDeleteMixin):
    """
    Represents a user's account, holding their balance in 'Loves'.
    """
    __tablename__ = 'user_accounts'

    user_id = db.Column(db.String(255), primary_key=True, nullable=False)
    # Numeric is the correct type for precise decimal values like currency.
    balance = db.Column(db.Numeric(precision=18, scale=4), default=Decimal('0.0'), nullable=False)

    def to_dict(self):
        return {
            "user_id": self.user_id,
            # Always serialize Decimals as strings to prevent precision loss.
            "balance": str(self.balance),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }

    def __repr__(self):
        return f"<UserAccount user_id={self.user_id} balance={self.balance}>"


# ==============================================================================
# 3. Consensus System Models
# ==============================================================================

class ConsensusNode(db.Model):
    """Represents a registered node in the consensus network."""
    __tablename__ = 'consensus_nodes'

    id = db.Column(db.String(255), primary_key=True)
    address = db.Column(db.String(255), unique=True, nullable=False)
    registered_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "address": self.address,
            "registered_at": self.registered_at.isoformat()
        }

    def __repr__(self):
        return f"<ConsensusNode id={self.id} address={self.address}>"

class ChainBlock(db.Model):
    """Represents a single block in the blockchain, stored in the database."""
    __tablename__ = 'chain_blocks'

    id = db.Column(db.Integer, primary_key=True) # The block's index
    timestamp = db.Column(db.Float, nullable=False)
    # Use the generic db.JSON type for portability.
    transactions = db.Column(db.JSON, nullable=False)
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

