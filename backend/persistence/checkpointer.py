"""
Production-grade PostgreSQL checkpointer for LangGraph.

Uses psycopg3 connection pooling for efficient database access.
The checkpointer automatically saves and restores full graph state
(messages, route data, disambiguation candidates) between invocations.
"""

import os
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
from backend.config import DATABASE_URL
from backend.utils.logger import AgentLogger

_pool: ConnectionPool | None = None
_checkpointer: PostgresSaver | None = None


def get_checkpointer() -> PostgresSaver:
    """
    Returns a PostgresSaver backed by a psycopg3 connection pool.
    
    Pool is created once (singleton) and reused across the app lifecycle.
    Checkpoint tables are auto-created on first call.
    
    Returns:
        PostgresSaver instance ready for use with LangGraph graphs.
    
    Raises:
        ValueError: If DATABASE_URL is not configured.
    """
    global _pool, _checkpointer
    
    if _checkpointer is not None:
        return _checkpointer
    
    if not DATABASE_URL:
        raise ValueError(
            "DATABASE_URL is not set. PostgreSQL is required for stateful agent persistence. "
            "Set DATABASE_URL in your .env file."
        )
    
    # Parse pool size from env (with sensible defaults)
    min_size = int(os.getenv("PG_POOL_MIN_SIZE", "2"))
    max_size = int(os.getenv("PG_POOL_MAX_SIZE", "10"))
    
    AgentLogger._print_box("🗄️  INITIALIZING CHECKPOINTER", AgentLogger.Colors.CYAN)
    print(f"  📦 Pool size: {min_size}-{max_size} connections")
    print(f"  🔗 Database: {_mask_connection_string(DATABASE_URL)}")
    
    _pool = ConnectionPool(
        conninfo=DATABASE_URL,
        min_size=min_size,
        max_size=max_size,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,  # Avoids issues with pgBouncer/connection poolers
        }
    )
    
    _checkpointer = PostgresSaver(conn=_pool)
    
    # Auto-create checkpoint tables (idempotent)
    _checkpointer.setup()
    
    print(f"  ✅ Checkpointer ready (tables created/verified)")
    AgentLogger.separator()
    
    return _checkpointer


def shutdown_pool() -> None:
    """
    Cleanly close all database connections in the pool.
    Call this on application shutdown.
    """
    global _pool, _checkpointer
    
    if _pool is not None:
        _pool.close()
        _pool = None
        _checkpointer = None
        print("🗄️  Checkpointer pool closed")


def _mask_connection_string(conn_str: str) -> str:
    """Mask password in connection string for safe logging."""
    # Handle postgresql://user:password@host format
    if "@" in conn_str and ":" in conn_str:
        try:
            prefix, rest = conn_str.split("://", 1)
            if "@" in rest:
                user_pass, host = rest.split("@", 1)
                if ":" in user_pass:
                    user, _ = user_pass.split(":", 1)
                    return f"{prefix}://{user}:****@{host}"
        except ValueError:
            pass
    return "****"
