# peoples_coin/models/tag.py

import uuid
from sqlalchemy import Column, String, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from peoples_coin.extensions import db

class Tag(db.Model):
    __tablename__ = "tags"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), unique=True, nullable=False)

    # --- Relationships ---
    # These are defined via the join tables
    goodwill_actions = relationship("GoodwillAction", secondary="goodwill_action_tags", back_populates="tags")
    proposals = relationship("Proposal", secondary="proposal_tags", back_populates="tags")

    __table_args__ = (
        CheckConstraint("name <> ''", name='check_tag_name_not_empty'),
    )

    def to_dict(self):
        """Serializes the Tag object to a dictionary."""
        return {
            "id": str(self.id),
            "name": self.name,
        }
