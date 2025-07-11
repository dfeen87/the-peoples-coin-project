# /Users/donfeeney/peoples_coin/peoples_coin/db/models.py

from datetime import datetime, timezone
from typing import Dict, Any
# Import specific types from SQLAlchemy if needed directly, but prefer db.Column etc.
# from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Index, event
from sqlalchemy import Index, event # Only import non-column related types directly
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.dialects.sqlite import JSON # Explicitly import JSON for SQLite

# CRITICAL: Import the db instance from the same package (db.py)
# This assumes db.py defines `db = SQLAlchemy()`
from .db import db

# --- MODEL DEFINITIONS ---

class DataEntry(db.Model): # Inherit from db.Model
    """
    SQLAlchemy model for data entries with processing status and timestamps.
    """
    __tablename__ = 'data_entries'
    __table_args__ = (
        db.Index('idx_processed_created_at', 'processed', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    value = db.Column(db.String(255), nullable=True)
    processed = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self) -> str:
        return (f"<DataEntry(id={self.id}, value={self.value!r}, "
                        f"processed={self.processed}, created_at={self.created_at}, "
                        f"updated_at={self.updated_at}, deleted_at={self.deleted_at})>")

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the object to a dictionary.
        """
        return {
            'id': self.id,
            'value': self.value,
            'processed': self.processed,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DataEntry":
        """
        Create a DataEntry instance from a dictionary.
        """
        return cls(
            value=data.get('value'),
            processed=data.get('processed', False),
            created_at=data.get('created_at', datetime.now(timezone.utc)),
            updated_at=data.get('updated_at', datetime.now(timezone.utc)),
            deleted_at=data.get('deleted_at')
        )

    def validate(self):
        """
        Validate model constraints before database operations.
        """
        if self.value and len(self.value) > 255:
            raise ValueError("Value exceeds maximum allowed length (255).")

    @hybrid_property
    def is_active(self) -> bool:
        """
        Returns True if the entry is active (not processed and not deleted).
        """
        return not self.processed and self.deleted_at is None

# --- NEW GoodwillAction Model for the Metabolic System ---
class GoodwillAction(db.Model): # Inherit from db.Model
    """
    Represents a verified goodwill action, serving as the input for the Metabolic System.
    This action will be processed by AILEE to determine its resonance and lead to token minting.
    """
    __tablename__ = 'goodwill_actions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), nullable=False, index=True)
    action_type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    # JSON type for contextual_data allows flexible storage of additional details
    contextual_data = db.Column(JSON, default={}) # Use JSON from sqlalchemy.dialects.sqlite
    
    # Fields to be populated after AILEE processing
    raw_goodwill_score = db.Column(db.Integer, default=0, nullable=False) # e.g., 1-100, before resonance
    resonance_score = db.Column(db.Integer, default=0, nullable=False)    # 0-100, AILEE's final score for minting
    
    # --- ADDED FOR ASYNCHRONOUS PROCESSING ---
    status = db.Column(db.String(50), default='pending', nullable=False) # e.g., 'pending', 'processing', 'completed', 'failed'
    processed_at = db.Column(db.DateTime, nullable=True) # Timestamp when AILEE processed it
    
    minted_token_id = db.Column(db.String(255), nullable=True, unique=True) # Link to the token minted

    def __repr__(self):
        return (f"<GoodwillAction(id={self.id}, user_id='{self.user_id}', "
                        f"action_type='{self.action_type}', resonance_score={self.resonance_score}, "
                        f"status='{self.status}')>")

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
            "minted_token_id": self.minted_token_id
        }

class EventLog(db.Model): # Inherits from db.Model for consistency
    """
    Logs significant events within the system.
    """
    __tablename__ = 'event_logs' # Changed to plural for consistency

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_type = db.Column(db.String(64), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "event_type": self.event_type,
            "message": self.message,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }

    def __repr__(self):
        return f"<EventLog(id={self.id}, event_type={self.event_type}, timestamp={self.timestamp})>"

# --- SQLAlchemy Event Listeners for DataEntry ---
# These are correctly placed after the model definitions they apply to.
@event.listens_for(DataEntry, 'before_update', propagate=True)
def receive_before_update(mapper, connection, target):
    """
    Automatically update the 'updated_at' timestamp before update.
    """
    target.updated_at = datetime.now(timezone.utc)

@event.listens_for(DataEntry, 'before_insert', propagate=True)
def receive_before_insert(mapper, connection, target):
    """
    Validate model before insert.
    """
    target.validate()



