"""
CLI test script for Nav AI Assistant (stateful).

Tests the supervisor agent with PostgreSQL checkpointing.
Each test session maintains conversation state across turns.
"""

from backend.agents.routing_engine import routing_engine
from backend.agents.search_agent import run_search_agent
from backend.agents.supervisor_agent import run_supervisor
from backend.persistence.checkpointer import get_checkpointer, shutdown_pool
import json
import uuid


def test_routing_engine():
    """Test the routing engine (stateless, pure API)."""
    print("=== Testing Routing Engine ===\n")
    
    location_a = input("Enter starting location: ")
    location_b = input("Enter destination: ")
    
    print(f"\nFinding route from {location_a} to {location_b}...\n")
    
    route_data = routing_engine(location_a, location_b)
    
    print("Route Data:")
    print(json.dumps(route_data, indent=2))
    
    return route_data


def test_search_agent(route_data=None):
    """Test the search agent (stateless)."""
    print("\n\n=== Testing Search Agent ===\n")
    
    query = input("Enter search query (e.g., 'Find gas stations along route'): ")
    
    result = run_search_agent(query, route_data=route_data)
    
    print("\n=== Search Result ===")
    print(result["messages"][-1].content)


def test_stateful_conversation():
    """Test stateful multi-turn conversation via supervisor."""
    print("\n=== Testing Stateful Conversation ===")
    print("Type 'quit' to exit. State is persisted between turns.\n")
    
    checkpointer = get_checkpointer()
    session_id = str(uuid.uuid4())
    
    print(f"Session ID: {session_id}\n")
    
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            break
        
        result = run_supervisor(
            user_message=user_input,
            session_id=session_id,
            checkpointer=checkpointer,
            location=None  # No GPS in CLI mode
        )
        
        print(f"\nAssistant: {result['message']}")
        
        if result.get("route_data"):
            rd = result["route_data"]
            print(f"  📏 Route: {rd.get('distance_km')} km, {rd.get('time_minutes')} min")
        
        if result.get("location_candidates"):
            print(f"  📍 {len(result['location_candidates'])} location options shown")
        
        print()
    
    shutdown_pool()
    print("\nSession ended. State is saved in PostgreSQL.")


if __name__ == "__main__":
    print("Nav AI Assistant - Testing\n")
    print("1. Test Routing Engine (stateless)")
    print("2. Test Search Agent (stateless)")
    print("3. Test Both (Route + Search)")
    print("4. Test Stateful Conversation (NEW)")
    
    choice = input("\nChoose option (1/2/3/4): ")
    
    if choice == "1":
        test_routing_engine()
    elif choice == "2":
        test_search_agent()
    elif choice == "3":
        route_data = test_routing_engine()
        test_search_agent(route_data)
    elif choice == "4":
        test_stateful_conversation()
    else:
        print("Invalid choice")
