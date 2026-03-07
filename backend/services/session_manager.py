import redis
import json
from datetime import datetime
from typing import List, Dict, Optional
from backend.config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD

class SessionManager:
    def __init__(self):
        self.redis = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5
        )
        self.TTL = 6 * 60 * 60  # 6 hours
    
    def save_message(self, session_id: str, message: str, role: str) -> bool:
        """Save a message to the session."""
        try:
            key = f"session:{session_id}:messages"
            data = {
                "role": role,
                "content": message,
                "timestamp": datetime.now().isoformat()
            }
            self.redis.rpush(key, json.dumps(data))
            self.redis.expire(key, self.TTL)
            return True
        except Exception as e:
            print(f"Error saving message: {e}")
            return False
    
    def get_messages(self, session_id: str) -> List[Dict]:
        """Get all messages for a session."""
        try:
            key = f"session:{session_id}:messages"
            messages = self.redis.lrange(key, 0, -1)
            return [json.loads(m) for m in messages]
        except Exception as e:
            print(f"Error getting messages: {e}")
            return []
    
    def save_route_data(self, session_id: str, route_data: dict) -> bool:
        """Save route data for a session."""
        try:
            key = f"session:{session_id}:route"
            self.redis.setex(key, self.TTL, json.dumps(route_data))
            return True
        except Exception as e:
            print(f"Error saving route: {e}")
            return False
    
    def get_route_data(self, session_id: str) -> Optional[dict]:
        """Get route data for a session."""
        try:
            key = f"session:{session_id}:route"
            data = self.redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            print(f"Error getting route: {e}")
            return None
    
    def save_user_mapping(self, session_id: str, user_id: str) -> bool:
        """Map session to user."""
        try:
            key = f"session:{session_id}:user"
            self.redis.setex(key, self.TTL, user_id)
            return True
        except Exception as e:
            print(f"Error saving user mapping: {e}")
            return False
    
    def get_user_id(self, session_id: str) -> Optional[str]:
        """Get user_id for a session."""
        try:
            key = f"session:{session_id}:user"
            return self.redis.get(key)
        except Exception as e:
            print(f"Error getting user_id: {e}")
            return None
    
    def touch_session(self, session_id: str):
        """Reset TTL on session activity."""
        try:
            keys = [
                f"session:{session_id}:messages",
                f"session:{session_id}:route",
                f"session:{session_id}:user"
            ]
            for key in keys:
                if self.redis.exists(key):
                    self.redis.expire(key, self.TTL)
        except Exception as e:
            print(f"Error touching session: {e}")
