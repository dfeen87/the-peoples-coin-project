# peoples_coin/models/audit_log.py

import uuid
from sqlalchemy import (
    Column, String, DateTime, func, ForeignKey
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ENUM, JSONB
from peoples_coin.extensions import db

class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True)
    
    action_type = Column(
        ENUM('USER_LOGIN', 'USER_UPDATE_EMAIL', 'ROLE_GRANTED', 'ROLE_REVOKED', 'PROPOSAL_STATUS_CHANGED', 'GOODWILL_ACTION_VERIFIED', 'SETTINGS_CHANGED', 'CONTENT_REPORT_REVIEWED', name='audited_action', create_type=False),
        nullable=False
    )
    
    target_entity_id = Column(String(255), nullable=True)
    details = Column(JSONB, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationship to link back to the UserAccount model
    actor = relationship("UserAccount", back_populates="audit_logs")

    def to_dict(self):
        """Serializes the AuditLog object to a dictionary."""
        return {
            "id": str(self.id),
            "actor_user_id": str(self.actor_user_id) if self.actor_user_id else None,
            "action_type": self.action_type,
            "target_entity_id": self.target_entity_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
