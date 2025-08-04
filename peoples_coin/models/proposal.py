import uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ENUM
from sqlalchemy import (
    Column, String, Text, DateTime, Numeric, JSON, func
)
from sqlalchemy.orm import relationship
from peoples_coin.extensions import db
from peoples_coin.db_types import JSONType, UUIDType, EnumType


class Proposal(db.Model):
    __tablename__ = "proposals"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposer_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(
        EnumType('DRAFT', 'ACTIVE', 'CLOSED', 'REJECTED', name='proposal_status'),
        nullable=False,
        server_default='DRAFT'
    )
    vote_start_time = Column(DateTime(timezone=True), nullable=True)
    vote_end_time = Column(DateTime(timezone=True), nullable=True)
    required_quorum = Column(Numeric(5, 2), nullable=False, default=0)
    proposal_type = Column(String(100), nullable=False)
    details = Column(JSONType, nullable=True, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    proposer = relationship("UserAccount", backref="proposals")

    def to_dict(self):
        return {
            "id": str(self.id),
            "proposer_user_id": str(self.proposer_user_id) if self.proposer_user_id else None,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "vote_start_time": self.vote_start_time.isoformat() if self.vote_start_time else None,
            "vote_end_time": self.vote_end_time.isoformat() if self.vote_end_time else None,
            "required_quorum": float(self.required_quorum),
            "proposal_type": self.proposal_type,
            "details": self.details,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
