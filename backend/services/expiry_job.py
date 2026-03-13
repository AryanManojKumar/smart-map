"""
Expiry Job — Cleanup-only background task.

Runs hourly via APScheduler. Deletes conversations that have been
summarized AND are older than 24 hours. No LLM calls — summarization
is triggered by the user clicking "New Chat".
"""

from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from backend.database.db import SessionLocal
from backend.models.conversation import Conversation
from backend.utils.logger import AgentLogger

# Module-level scheduler instance
_scheduler: BackgroundScheduler | None = None

# How old a summarized conversation must be before cleanup
CLEANUP_HOURS = 24


def _run_cleanup_cycle():
    """
    Cleanup cycle: delete summarized conversations older than 24 hours.
    This is purely a storage janitor — no LLM calls.
    """
    AgentLogger.info("🧹 Running conversation cleanup cycle...")

    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=CLEANUP_HOURS)

        # Delete summarized conversations older than cutoff
        deleted_count = (
            db.query(Conversation)
            .filter(
                Conversation.updated_at < cutoff,
                Conversation.is_summarized == True,  # noqa: E712
            )
            .delete(synchronize_session="fetch")
        )

        if deleted_count > 0:
            db.commit()
            AgentLogger.info(f"🧹 Cleaned up {deleted_count} old summarized conversation(s)")
        else:
            AgentLogger.info("🧹 No conversations to clean up")

    except Exception as e:
        AgentLogger.error(f"🧹 Cleanup cycle error: {e}")
        db.rollback()
    finally:
        db.close()


def start_expiry_scheduler():
    """Start the background scheduler for conversation cleanup."""
    global _scheduler

    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _run_cleanup_cycle,
        trigger=IntervalTrigger(hours=1),
        id="conversation_cleanup",
        name="Clean up old summarized conversations",
        replace_existing=True,
    )
    _scheduler.start()
    AgentLogger.info("🧹 Conversation cleanup scheduler started (runs every 1 hour)")
    return _scheduler


def stop_expiry_scheduler():
    """Stop the background scheduler."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        AgentLogger.info("🧹 Conversation cleanup scheduler stopped")
