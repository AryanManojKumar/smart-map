import requests
from langchain_core.tools import tool
from backend.config import GRAPHHOPPER_API_KEY, GRAPHHOPPER_BASE_URL
from backend.utils.logger import AgentLogger

@tool
def get_route(location_a: str, location_b: str, vehicle: str = "car") -> dict:
    """Get route directions between two locations using GraphHopper API.
    
    Args:
        location_a: Starting location (address or coordinates)
        location_b: Destination location (address or coordinates)
        vehicle: Vehicle type (car, bike, foot)
    
    Returns:
        Dictionary containing route information including distance, time, polyline, and directions
    """
    
    AgentLogger.routing_start(location_a, location_b)
    
    geocode_url = f"{GRAPHHOPPER_BASE_URL}/geocode"
    
    # Geocode location A
    response_a = requests.get(
        geocode_url, params={"q": location_a, "key": GRAPHHOPPER_API_KEY}
    )
    response_a.raise_for_status()
    coords_a = response_a.json()["hits"][0]["point"]
    AgentLogger.routing_geocoding(location_a, coords_a)
    
    # Geocode location B
    response_b = requests.get(
        geocode_url, params={"q": location_b, "key": GRAPHHOPPER_API_KEY}
    )
    response_b.raise_for_status()
    coords_b = response_b.json()["hits"][0]["point"]
    AgentLogger.routing_geocoding(location_b, coords_b)
    
    # Get route
    AgentLogger.routing_calculating()
    route_url = f"{GRAPHHOPPER_BASE_URL}/route"
    route_response = requests.get(
        route_url,
        params={
            "point": [
                f"{coords_a['lat']},{coords_a['lng']}",
                f"{coords_b['lat']},{coords_b['lng']}",
            ],
            "vehicle": vehicle,
            "locale": "en",
            "instructions": "true",
            "calc_points": "true",
            "points_encoded": "false",
            "key": GRAPHHOPPER_API_KEY,
        },
    )
    route_response.raise_for_status()
    route_data = route_response.json()
    
    path = route_data["paths"][0]
    
    # Extract polyline coordinates
    polyline = [[point[1], point[0]] for point in path["points"]["coordinates"]]
    
    result = {
        "distance_km": round(path["distance"] / 1000, 2),
        "time_minutes": round(path["time"] / 60000, 2),
        "instructions": [instr["text"] for instr in path["instructions"]],
        "polyline": polyline,
        "start_point": {"lat": coords_a["lat"], "lng": coords_a["lng"]},
        "end_point": {"lat": coords_b["lat"], "lng": coords_b["lng"]},
        "from": location_a,
        "to": location_b,
    }
    
    AgentLogger.routing_complete(result)
    AgentLogger.separator()
    
    return result
