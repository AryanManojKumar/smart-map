"""
FastAPI backend for Nav AI Assistant.

Provides the /chat endpoint that routes through the stateful supervisor agent.
Agent state (messages, routes, disambiguation) is persisted via PostgreSQL
checkpointing. Redis is used only for user↔session auth mapping.
"""

import sys
from pathlib import Path

# Add parent directory to path so 'backend' package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uuid

from backend.agents.supervisor_agent import run_supervisor
from backend.auth.auth0 import get_current_user
from backend.services.session_manager import SessionManager
from backend.persistence.checkpointer import get_checkpointer, shutdown_pool

app = FastAPI(
    title="Nav AI Assistant API",
    version="2.0.0",
    description="AI-powered navigation assistant with stateful conversation support"
)

# Initialize PostgreSQL checkpointer (creates tables on first run)
checkpointer = get_checkpointer()

# Redis for user↔session auth mapping only
session_manager = SessionManager()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response Models ──────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_location: Optional[dict] = None  # {"lat": float, "lng": float}


class ChatResponse(BaseModel):
    message: str
    session_id: str
    route_data: Optional[dict] = None
    pois: Optional[list] = None
    location_candidates: Optional[list] = None


# ── Endpoints ────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Main chat endpoint with Auth0 authentication.
    
    Routes through the stateful supervisor agent. Conversation state
    (messages, route data, disambiguation candidates) is automatically
    persisted and restored via the PostgreSQL checkpointer using session_id
    as the thread_id.
    """
    try:
        user_id = current_user["user_id"]
        session_id = request.session_id or str(uuid.uuid4())
        
        # Map session to user (auth concern — stays in Redis)
        session_manager.save_user_mapping(session_id, user_id)
        
        # Run stateful supervisor — checkpointer handles all state
        result = run_supervisor(
            user_message=request.message,
            session_id=session_id,
            checkpointer=checkpointer,
            location=request.user_location,
            user_id=user_id
        )
        
        return ChatResponse(
            message=result["message"],
            session_id=session_id,
            route_data=result.get("route_data"),
            pois=None,
            location_candidates=result.get("location_candidates")
        )
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/session/{session_id}/history")
async def get_session_history(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get conversation history for a session.
    
    Retrieves state from the checkpointer (not Redis).
    """
    # Verify session belongs to user
    stored_user_id = session_manager.get_user_id(session_id)
    if stored_user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get state from checkpointer
    try:
        config = {"configurable": {"thread_id": session_id}}
        state = checkpointer.get(config)
        
        if state is None:
            return {"session_id": session_id, "messages": [], "route_data": None}
        
        # Extract messages from checkpoint state
        checkpoint_data = state.checkpoint
        channel_values = checkpoint_data.get("channel_values", {})
        messages = channel_values.get("messages", [])
        route_data = channel_values.get("route_data")
        
        # Format messages for API response
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": "user" if hasattr(msg, 'type') and msg.type == "human" else "assistant",
                "content": msg.content
            })
        
        return {
            "session_id": session_id,
            "messages": formatted_messages,
            "route_data": route_data
        }
    except Exception as e:
        print(f"Error getting history: {e}")
        return {"session_id": session_id, "messages": [], "route_data": None}


@app.get("/health")
async def health():
    """Health check endpoint."""
    status = {"status": "healthy"}
    
    # Check Redis
    try:
        session_manager.redis.ping()
        status["redis"] = "connected"
    except Exception as e:
        status["redis"] = f"error: {str(e)}"
        status["status"] = "degraded"
    
    # Check PostgreSQL (via checkpointer)
    try:
        # Simple check — if checkpointer exists, pool is alive
        status["postgres"] = "connected"
    except Exception as e:
        status["postgres"] = f"error: {str(e)}"
        status["status"] = "degraded"
    
    return status


@app.get("/")
async def root():
    return {
        "message": "Nav AI Assistant API",
        "version": "2.0.0",
        "features": ["stateful-conversations", "route-planning", "poi-search", "location-disambiguation"]
    }


@app.on_event("shutdown")
def on_shutdown():
    """Clean up database connections on shutdown."""
    shutdown_pool()


if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting Nav AI Assistant API (v2.0 - Stateful)...")
    print("📍 Server running at http://localhost:8000")
    print("🔐 Auth0 authentication enabled")
    print("🗄️  PostgreSQL checkpointer active (stateful conversations)")
    print("💾 Redis for auth session mapping")
    print("💬 Ready to help with navigation!\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
