"""
LangGraph state definitions for all agents.

SupervisorState is the primary stateful type — all fields are persisted
by the PostgreSQL checkpointer between conversation turns.
"""

from typing import TypedDict, Annotated, Sequence, Optional, List, Dict, Any
from langchain_core.messages import BaseMessage
import operator


class SupervisorState(TypedDict):
    """
    Full state for the supervisor agent graph.
    
    Persisted by the checkpointer across invocations via thread_id.
    The `messages` field uses operator.add so new messages are appended
    to the existing history (not replaced).
    """
    # Conversation history — auto-accumulated via operator.add
    messages: Annotated[Sequence[BaseMessage], operator.add]
    
    # Last computed route data (polyline, distance, time, etc.)
    route_data: Optional[Dict[str, Any]]
    
    # Pre-built route context document for conversational Q&A about active route
    route_context: Optional[str]
    
    # User's current GPS location {lat, lng}
    location: Optional[Dict[str, float]]
    
    # Current detected intent: routing | search | conversation | route_question | disambiguation | error
    current_intent: str
    
    # Location disambiguation state (stored between turns)
    # Format: {"candidates": [...], "context": {"location_a": ..., "location_b": ..., "ambiguous_field": ...}}
    pending_candidates: Optional[Dict[str, Any]]
    
    # Location candidates to return to frontend for map display
    location_candidates: Optional[List[Dict[str, Any]]]
    
    # Intra-graph node communication (transient, used within a single invocation)
    _routing_params: Optional[Dict[str, str]]  # {location_a, location_b} from router → routing_node
    _search_params: Optional[Dict[str, str]]   # {poi_type} from router → search_node


class SearchAgentState(TypedDict):
    """State for the POI search sub-agent."""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    route_data: dict
    location: dict
    search_results: list
