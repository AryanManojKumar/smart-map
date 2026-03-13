"""
Conversation model — tracks user conversations with metadata.

Conversations expire after 24 hours. Before expiry, the background job
extracts knowledge and stores it in user_knowledge.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Boolean, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from backend.database.db import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    title = Column(String, default="New Chat")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_message = Column(Text, nullable=True)
    is_summarized = Column(Boolean, default=False)

    __table_args__ = (
        Index("idx_conversations_user_updated", "user_id", "updated_at"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "session_id": self.session_id,
            "user_id": self.user_id,
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_message": self.last_message,
        }
