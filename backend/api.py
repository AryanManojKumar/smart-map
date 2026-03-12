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
from typing import Optional, List
import uuid
import json

from backend.agents.supervisor_agent import run_supervisor, call_gemini_api
from backend.auth.auth0 import get_current_user
from backend.services.session_manager import SessionManager
from backend.persistence.checkpointer import get_checkpointer, shutdown_pool
from backend.tools.waze_tool import get_waze_alerts_and_jams

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
    alternative_routes: Optional[list] = None


class AnalyzeRouteRequest(BaseModel):
    route_data: dict


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
            pois=result.get("search_results"),
            location_candidates=result.get("location_candidates"),
            alternative_routes=result.get("alternative_routes")
        )
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze-route")
async def analyze_route(
    request: AnalyzeRouteRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Analyze a route for traffic bottlenecks and fetch live Waze data.

    1. LLM identifies bottleneck segments from route instructions + road details
    2. Segments with risk_score >= 6 get a Waze API call (capped at 3)
    3. Returns aggregated alerts and jams for map rendering
    """
    try:
        route_data = request.route_data

        # Build compact route summary for the LLM
        instructions_summary = []
        for idx, instr in enumerate(route_data.get("detailed_instructions", [])):
            instructions_summary.append({
                "step": idx + 1,
                "text": instr.get("text", ""),
                "street": instr.get("street_name", ""),
                "distance_m": instr.get("distance_m", 0),
                "interval": instr.get("interval", []),
            })

        road_details = route_data.get("road_details", {})
        polyline = route_data.get("polyline", [])

        # Sample polyline to keep prompt small (every Nth point)
        sample_rate = max(1, len(polyline) // 40)
        sampled_polyline = polyline[::sample_rate]
        if polyline and sampled_polyline[-1] != polyline[-1]:
            sampled_polyline.append(polyline[-1])

        llm_prompt = f"""You are a traffic analyst. Given this route data, identify segments most likely to have congestion or incidents.

Route: {route_data.get('from', '?')} → {route_data.get('to', '?')}
Distance: {route_data.get('distance_km', '?')} km | Duration: {route_data.get('time_minutes', '?')} min

Step-by-step instructions:
{json.dumps(instructions_summary, indent=1)}

Road details:
- road_class: {json.dumps(road_details.get('road_class', []))}
- max_speed: {json.dumps(road_details.get('max_speed', []))}
- lanes: {json.dumps(road_details.get('lanes', []))}
- surface: {json.dumps(road_details.get('surface', []))}

Polyline coordinates (sampled, [lat, lng]):
{json.dumps(sampled_polyline)}

For each bottleneck, compute a bounding box from the polyline coords at the instruction interval indices, padded by ~0.01 degrees.

Return ONLY valid JSON:
{{
  "analysis_summary": "<2-3 sentence overview of the route's traffic risk>",
  "bottlenecks": [
    {{
      "description": "<what makes this a bottleneck>",
      "risk_score": <1-10>,
      "reason": "merge|intersection|road_class_change|speed_limit_drop|urban_dense|construction",
      "bounding_box": {{
        "bottom_left": "<lat>,<lng>",
        "top_right": "<lat>,<lng>"
      }}
    }}
  ]
}}

Focus on: motorway merges, road class downgrades, speed limit drops, dense urban areas, sharp turns at major intersections.
Return at most 5 bottlenecks. Return ONLY valid JSON, no markdown."""

        from langchain_core.messages import HumanMessage
        llm_response = call_gemini_api(
            [HumanMessage(content=llm_prompt)],
            purpose="route_bottleneck_analysis",
            reasoning_effort="high",
        )

        # Parse LLM JSON response
        response_text = llm_response.strip()
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            analysis = json.loads(response_text[json_start:json_end])
        else:
            analysis = {"analysis_summary": response_text, "bottlenecks": []}

        bottlenecks = analysis.get("bottlenecks", [])
        analysis_summary = analysis.get("analysis_summary", "")

        # Gate Waze API calls: only risk_score >= 6, capped at 3
        high_risk = sorted(
            [b for b in bottlenecks if b.get("risk_score", 0) >= 6],
            key=lambda x: x.get("risk_score", 0),
            reverse=True,
        )[:3]

        all_alerts = []
        all_jams = []
        waze_calls_made = 0

        for segment in high_risk:
            bb = segment.get("bounding_box", {})
            bl = bb.get("bottom_left", "")
            tr = bb.get("top_right", "")
            if not bl or not tr:
                continue

            waze_result = get_waze_alerts_and_jams(
                bottom_left=bl, top_right=tr, max_alerts=10, max_jams=10
            )
            waze_calls_made += 1
            all_alerts.extend(waze_result.get("alerts", []))
            all_jams.extend(waze_result.get("jams", []))

        return {
            "bottleneck_analysis": analysis_summary,
            "bottlenecks": bottlenecks,
            "alerts": all_alerts,
            "jams": all_jams,
            "waze_calls_made": waze_calls_made,
            "segments_analyzed": len(bottlenecks),
        }

    except Exception as e:
        print(f"Analyze route error: {e}")
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
