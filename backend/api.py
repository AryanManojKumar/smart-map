from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sys
from pathlib import Path
from typing import Optional
import uuid

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.agents.supervisor_agent import run_supervisor
from backend.auth.auth0 import get_current_user
from backend.services.session_manager import SessionManager
from backend.database.db import init_db

app = FastAPI()

# Initialize database
init_db()

# Initialize session manager
session_manager = SessionManager()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    message: str
    session_id: str
    route_data: Optional[dict] = None
    pois: Optional[list] = None

@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Main chat endpoint with Auth0 authentication.
    Routes through supervisor agent with session management.
    """
    
    try:
        user_id = current_user["user_id"]
        
        # Generate or use existing session_id
        session_id = request.session_id or str(uuid.uuid4())
        
        # Map session to user
        session_manager.save_user_mapping(session_id, user_id)
        
        # Get conversation history from Redis
        messages = session_manager.get_messages(session_id)
        route_data = session_manager.get_route_data(session_id)
        
        # Save user message
        session_manager.save_message(session_id, request.message, "user")
        
        # Run supervisor with context
        result = run_supervisor(
            request.message,
            route_data=route_data,
            location=None
        )
        
        # Save assistant response
        session_manager.save_message(session_id, result["message"], "assistant")
        
        # Save route data if returned
        if result.get("route_data"):
            session_manager.save_route_data(session_id, result["route_data"])
        
        # Touch session to reset TTL
        session_manager.touch_session(session_id)
        
        return ChatResponse(
            message=result["message"],
            session_id=session_id,
            route_data=result.get("route_data"),
            pois=None
        )
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/session/{session_id}/history")
async def get_session_history(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get conversation history for a session."""
    
    # Verify session belongs to user
    stored_user_id = session_manager.get_user_id(session_id)
    if stored_user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    messages = session_manager.get_messages(session_id)
    route_data = session_manager.get_route_data(session_id)
    
    return {
        "session_id": session_id,
        "messages": messages,
        "route_data": route_data
    }

@app.get("/health")
async def health():
    """Health check endpoint."""
    try:
        # Test Redis
        session_manager.redis.ping()
        return {"status": "healthy", "redis": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@app.get("/")
async def root():
    return {"message": "Nav AI Assistant API", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting Nav AI Assistant API...")
    print("📍 Server running at http://localhost:8000")
    print("🔐 Auth0 authentication enabled")
    print("💾 Redis session storage active")
    print("💬 Ready to help with navigation!\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
