# peoples_coin/models/proposal_tag.py

from sqlalchemy import Column, ForeignKey, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from peoples_coin.extensions import db

class ProposalTag(db.Model):
    __tablename__ = "proposal_tags"

    proposal_id = Column(PG_UUID(as_uuid=True), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False)
    tag_id = Column(PG_UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint('proposal_id', 'tag_id'),
    )
