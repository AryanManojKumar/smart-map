"""
Session Manager — Redis-based user↔session auth mapping.

Agent state (messages, routes, disambiguation) is handled by the
LangGraph PostgreSQL checkpointer. This module only manages the
auth-level concern of mapping session IDs to user IDs.
"""

import redis
from typing import Optional
from backend.config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD


class SessionManager:
    """Manages session-to-user mapping in Redis for auth verification."""
    
    def __init__(self):
        self.redis = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5
        )
        self.TTL = 24 * 60 * 60  # 24 hours (longer TTL since this is just auth mapping)
    
    def save_user_mapping(self, session_id: str, user_id: str) -> bool:
        """Map a session to a user (for auth ownership checks)."""
        try:
            key = f"session:{session_id}:user"
            self.redis.setex(key, self.TTL, user_id)
            return True
        except Exception as e:
            print(f"Error saving user mapping: {e}")
            return False
    
    def get_user_id(self, session_id: str) -> Optional[str]:
        """Get the user_id that owns a session."""
        try:
            key = f"session:{session_id}:user"
            return self.redis.get(key)
        except Exception as e:
            print(f"Error getting user_id: {e}")
            return None
