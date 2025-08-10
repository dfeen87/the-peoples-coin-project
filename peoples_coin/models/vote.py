# peoples_coin/models/vote.py

import uuid
from sqlalchemy import Column, String, Text, DateTime, func, UniqueConstraint, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ENUM
from peoples_coin.extensions import db

class Vote(db.Model):
    __tablename__ = "votes"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    voter_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id"), nullable=True)
    proposal_id = Column(PG_UUID(as_uuid=True), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False)
    
    # This correctly uses the ENUM type defined in your schema
    vote_value = Column(ENUM('FOR', 'AGAINST', 'ABSTAIN', name='vote_option', create_type=False), nullable=False)
    
    rationale = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # --- CHANGE: Relationships updated for consistency ---
    # Use back_populates for a clear, two-way relationship link
    voter = relationship("UserAccount", back_populates="votes")
    proposal = relationship("Proposal", back_populates="votes")

    # This is the correct way to define a multi-column unique constraint
    __table_args__ = (
        UniqueConstraint('voter_user_id', 'proposal_id', name='unique_voter_proposal'),
    )

    def to_dict(self):
        """Serializes the Vote object to a dictionary."""
        return {
            "id": str(self.id),
            "voter_user_id": str(self.voter_user_id) if self.voter_user_id else None,
            "proposal_id": str(self.proposal_id),
            "vote_value": self.vote_value,
            "rationale": self.rationale,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
