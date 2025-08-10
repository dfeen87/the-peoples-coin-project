# peoples_coin/models/goodwill_action_tag.py

from sqlalchemy import Column, ForeignKey, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from peoples_coin.extensions import db

class GoodwillActionTag(db.Model):
    __tablename__ = "goodwill_action_tags"

    goodwill_action_id = Column(PG_UUID(as_uuid=True), ForeignKey("goodwill_actions.id", ondelete="CASCADE"), nullable=False)
    tag_id = Column(PG_UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint('goodwill_action_id', 'tag_id'),
    )
