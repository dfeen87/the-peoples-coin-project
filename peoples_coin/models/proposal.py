# peoples_coin/models/proposal.py

import uuid
from sqlalchemy import Column, String, Text, DateTime, Numeric, func, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ENUM, JSONB
from peoples_coin.extensions import db

class Proposal(db.Model):
    __tablename__ = "proposals"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposer_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    
    status = Column(
        ENUM('DRAFT', 'ACTIVE', 'CLOSED', 'REJECTED', name='proposal_status', create_type=False),
        nullable=False,
        server_default='DRAFT'
    )
    
    vote_start_time = Column(DateTime(timezone=True), nullable=True)
    vote_end_time = Column(DateTime(timezone=True), nullable=True)
    required_quorum = Column(Numeric(5, 2), nullable=False, default=0) # This was missing from the last schema version, but is correct.
    proposal_type = Column(String(100), nullable=False) # Same as above.
    details = Column(JSONB, nullable=True, server_default=func.text("'{}'::jsonb"))
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # --- ADDED: All relationships to other models ---
    proposer = relationship("UserAccount", back_populates="proposals")
    votes = relationship("Vote", back_populates="proposal", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="proposal", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary="proposal_tags", back_populates="proposals")


    def to_dict(self):
        """Serializes the Proposal object to a dictionary."""
        return {
            "id": str(self.id),
            "proposer_user_id": str(self.proposer_user_id) if self.proposer_user_id else None,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "vote_start_time": self.vote_start_time.isoformat() if self.vote_start_time else None,
            "vote_end_time": self.vote_end_time.isoformat() if self.vote_end_time else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
