# peoples_coin/models/comment.py

import uuid
from sqlalchemy import (
    Column, Text, DateTime, func, ForeignKey, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from peoples_coin.extensions import db

class Comment(db.Model):
    __tablename__ = "comments"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True)
    proposal_id = Column(PG_UUID(as_uuid=True), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=True)
    goodwill_action_id = Column(PG_UUID(as_uuid=True), ForeignKey("goodwill_actions.id", ondelete="CASCADE"), nullable=True)
    
    # --- FIXED: Self-referential relationship with ForeignKey to parent_comment_id
    parent_comment_id = Column(PG_UUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE"), nullable=True)
    
    content = Column(Text, nullable=False)
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # --- Relationships ---
    author = relationship("UserAccount", back_populates="comments")
    proposal = relationship("Proposal", back_populates="comments")
    goodwill_action = relationship("GoodwillAction", back_populates="comments")
    
    # --- FIXED: Self-referential relationship for threaded comments
    parent = relationship("Comment", remote_side=[id], back_populates="replies")
    replies = relationship("Comment", back_populates="parent", cascade="all, delete-orphan", primaryjoin="Comment.parent_comment_id == Comment.id")
    
    # --- Constraints ---
    __table_args__ = (
        CheckConstraint(
            '(proposal_id IS NOT NULL AND goodwill_action_id IS NULL) OR (proposal_id IS NULL AND goodwill_action_id IS NOT NULL)',
            name='chk_comment_has_one_target'
        ),
    )

    def to_dict(self):
        """Serializes the Comment object to a dictionary."""
        return {
            "id": str(self.id),
            "author_user_id": str(self.author_user_id) if self.author_user_id else None,
            "proposal_id": str(self.proposal_id) if self.proposal_id else None,
            "goodwill_action_id": str(self.goodwill_action_id) if self.goodwill_action_id else None,
            "parent_comment_id": str(self.parent_comment_id) if self.parent_comment_id else None,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "replies": [reply.to_dict() for reply in self.replies]
        }
