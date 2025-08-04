import uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ENUM
from sqlalchemy import (
    Column, String, Text, DateTime, func, UniqueConstraint, ForeignKey
)
from sqlalchemy.orm import relationship
from peoples_coin.extensions import db


class Vote(db.Model):
    __tablename__ = "votes"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    voter_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True)
    proposal_id = Column(PG_UUID(as_uuid=True), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False)
    vote_value = Column(
        ENUM('FOR', 'AGAINST', 'ABSTAIN', name='vote_option'),
        nullable=False
    )
    rationale = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    voter = relationship("UserAccount", backref="votes")
    proposal = relationship("Proposal", backref="votes")

    __table_args__ = (
        UniqueConstraint('voter_user_id', 'proposal_id', name='unique_voter_proposal'),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "voter_user_id": str(self.voter_user_id) if self.voter_user_id else None,
            "proposal_id": str(self.proposal_id),
            "vote_value": self.vote_value,
            "rationale": self.rationale,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

