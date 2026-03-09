"""
Database module — placeholder for future analytics/reporting.

Agent state persistence is handled by the LangGraph PostgreSQL checkpointer
(see backend/persistence/checkpointer.py). This module is preserved for
any future database needs beyond agent state.
"""

# The checkpointer creates and manages its own tables:
#   - checkpoints
#   - checkpoint_blobs  
#   - checkpoint_writes
#
# No additional SQLAlchemy models are needed for core agent functionality.
# If you need custom analytics or reporting tables in the future,
# add them here using SQLAlchemy.

def init_db():
    """No-op — checkpointer handles its own table creation."""
    pass
