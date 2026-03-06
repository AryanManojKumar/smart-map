from backend.tools.graphhopper_tool import get_route

def routing_engine(location_a: str, location_b: str, vehicle: str = "car"):
    """
    Routing Engine - Pure data fetcher for route information.
    No LLM, just returns structured route data.
    
    Args:
        location_a: Starting location
        location_b: Destination location
        vehicle: Vehicle type (car, bike, foot)
    
    Returns:
        Structured route data with coordinates, instructions, distance, time
    """
    return get_route.invoke({"location_a": location_a, "location_b": location_b, "vehicle": vehicle})
