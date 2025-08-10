# peoples_coin/models/content_report.py

import uuid
from sqlalchemy import (
    Column, String, Text, DateTime, func, ForeignKey
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ENUM
from peoples_coin.extensions import db

class ContentReport(db.Model):
    __tablename__ = "content_reports"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reporter_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    
    entity_type = Column(
        ENUM('PROPOSAL', 'COMMENT', 'GOODWILL_ACTION', 'USER_ACCOUNT', name='reportable_entity_type', create_type=False),
        nullable=False
    )
    entity_id = Column(PG_UUID(as_uuid=True), nullable=False)
    
    reason = Column(Text, nullable=False)
    
    status = Column(
        ENUM('PENDING_REVIEW', 'ACTION_TAKEN', 'DISMISSED', name='report_status', create_type=False),
        nullable=False,
        server_default='PENDING_REVIEW'
    )
    
    reviewer_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # --- Relationships ---
    reporter = relationship("UserAccount", foreign_keys=[reporter_user_id], back_populates="submitted_reports")
    reviewer = relationship("UserAccount", foreign_keys=[reviewer_user_id], back_populates="reviewed_reports")

    def to_dict(self):
        """Serializes the ContentReport object to a dictionary."""
        return {
            "id": str(self.id),
            "reporter_user_id": str(self.reporter_user_id),
            "entity_type": self.entity_type,
            "entity_id": str(self.entity_id),
            "reason": self.reason,
            "status": self.status,
            "reviewer_user_id": str(self.reviewer_user_id) if self.reviewer_user_id else None,
            "resolution_notes": self.resolution_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
