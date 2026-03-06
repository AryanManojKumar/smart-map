from backend.agents.routing_engine import routing_engine
from backend.agents.search_agent import run_search_agent
import json

def test_routing_engine():
    """Test the routing engine."""
    print("=== Testing Routing Engine ===\n")
    
    location_a = input("Enter starting location: ")
    location_b = input("Enter destination: ")
    
    print(f"\nFinding route from {location_a} to {location_b}...\n")
    
    route_data = routing_engine(location_a, location_b)
    
    print("Route Data:")
    print(json.dumps(route_data, indent=2))
    
    return route_data

def test_search_agent(route_data=None):
    """Test the search agent."""
    print("\n\n=== Testing Search Agent ===\n")
    
    query = input("Enter search query (e.g., 'Find gas stations along route'): ")
    
    result = run_search_agent(query, route_data=route_data)
    
    print("\n=== Search Result ===")
    print(result["messages"][-1].content)

if __name__ == "__main__":
    print("Nav AI Assistant - Testing\n")
    print("1. Test Routing Engine")
    print("2. Test Search Agent")
    print("3. Test Both (Route + Search)")
    
    choice = input("\nChoose option (1/2/3): ")
    
    if choice == "1":
        test_routing_engine()
    elif choice == "2":
        test_search_agent()
    elif choice == "3":
        route_data = test_routing_engine()
        test_search_agent(route_data)
    else:
        print("Invalid choice")
