from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.agents.supervisor_agent import run_supervisor

app = FastAPI()

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
    route_data: Optional[dict] = None
    location: Optional[dict] = None

class ChatResponse(BaseModel):
    message: str
    route_data: Optional[dict] = None
    pois: Optional[list] = None

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint that handles user messages.
    Routes through supervisor agent.
    """
    
    try:
        result = run_supervisor(
            request.message,
            route_data=request.route_data,
            location=request.location
        )
        
        return ChatResponse(
            message=result["message"],
            route_data=result.get("route_data"),
            pois=None
        )
    except Exception as e:
        print(f"Error: {e}")
        return ChatResponse(
            message="Sorry, I encountered an error. Please try again.",
            route_data=None,
            pois=None
        )

@app.get("/")
async def root():
    return {"message": "Nav AI Assistant API"}

if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting Nav AI Assistant API...")
    print("📍 Server running at http://localhost:8000")
    print("💬 Ready to help with navigation!\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
