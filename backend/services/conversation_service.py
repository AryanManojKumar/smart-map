"""
Conversation Service — CRUD operations for the conversations table.

Manages the lightweight conversation index that links users to their
chat sessions via Auth0 user_id.
"""

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from backend.models.conversation import Conversation


def upsert_conversation(db: Session, session_id: str, user_id: str, message: str) -> Conversation:
    """
    Create or update a conversation record.

    On first call (new session_id): creates a new row with auto-generated title.
    On subsequent calls: updates updated_at and last_message.
    """
    conv = db.query(Conversation).filter(Conversation.session_id == session_id).first()

    if conv is None:
        # New conversation — generate title from first message
        title = message[:50].strip()
        if len(message) > 50:
            title += "..."

        conv = Conversation(
            session_id=session_id,
            user_id=user_id,
            title=title,
            last_message=message[:200] if message else None,
        )
        db.add(conv)
    else:
        conv.updated_at = datetime.now(timezone.utc)
        conv.last_message = message[:200] if message else conv.last_message

    db.commit()
    db.refresh(conv)
    return conv


def get_user_conversations(db: Session, user_id: str) -> list[Conversation]:
    """List all conversations for a user, newest first."""
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )


def get_conversation(db: Session, session_id: str, user_id: str) -> Conversation | None:
    """Get a single conversation with ownership check."""
    return (
        db.query(Conversation)
        .filter(
            Conversation.session_id == session_id,
            Conversation.user_id == user_id,
        )
        .first()
    )


def delete_conversation(db: Session, session_id: str, user_id: str) -> bool:
    """Delete a conversation. Returns True if deleted, False if not found."""
    conv = get_conversation(db, session_id, user_id)
    if conv is None:
        return False
    db.delete(conv)
    db.commit()
    return True


def rename_conversation(db: Session, session_id: str, user_id: str, title: str) -> Conversation | None:
    """Rename a conversation. Returns updated conversation or None."""
    conv = get_conversation(db, session_id, user_id)
    if conv is None:
        return None
    conv.title = title
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(conv)
    return conv
