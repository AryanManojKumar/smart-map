"""
GraphHopper Routing Tool — geocodes locations and computes routes.

Handles both address strings and raw coordinate strings (lat,lng).
"""

import requests
from langchain_core.tools import tool
from backend.config import GRAPHHOPPER_API_KEY, GRAPHHOPPER_BASE_URL
from backend.utils.logger import AgentLogger


def _parse_coordinates(location: str):
    """
    Check if location is already coordinates (lat,lng).
    Returns {"lat": float, "lng": float} if yes, None if no.
    """
    try:
        parts = location.split(',')
        if len(parts) == 2:
            lat = float(parts[0].strip())
            lng = float(parts[1].strip())
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return {"lat": lat, "lng": lng}
    except (ValueError, AttributeError):
        pass
    return None


def _geocode(location: str) -> dict:
    """
    Geocode a location string to coordinates.
    If already coordinates, skip the API call.
    Returns {"lat": float, "lng": float}.
    """
    # Check if already coordinates
    coords = _parse_coordinates(location)
    if coords:
        AgentLogger.info(f"Skipping geocode — already coordinates: ({coords['lat']:.4f}, {coords['lng']:.4f})")
        return coords
    
    # Geocode via GraphHopper
    geocode_url = f"{GRAPHHOPPER_BASE_URL}/geocode"
    AgentLogger.api_call("GraphHopper Geocoding", geocode_url, payload_size=len(location))
    
    response = requests.get(
        geocode_url, params={"q": location, "key": GRAPHHOPPER_API_KEY}
    )
    response.raise_for_status()
    data = response.json()
    
    hits = data.get("hits", [])
    if not hits:
        raise ValueError(f"No geocoding results found for '{location}'")
    
    coords = {"lat": hits[0]["point"]["lat"], "lng": hits[0]["point"]["lng"]}
    AgentLogger.routing_geocoding(location, coords)
    return coords


@tool
def get_route(location_a: str, location_b: str, vehicle: str = "car") -> dict:
    """Get route directions between two locations using GraphHopper API.
    
    Args:
        location_a: Starting location (address or coordinates like "28.6,77.2")
        location_b: Destination location (address or coordinates)
        vehicle: Vehicle type (car, bike, foot)
    
    Returns:
        Dictionary containing route information including distance, time, polyline, and directions
    """
    
    AgentLogger.routing_start(location_a, location_b)
    
    # Geocode both locations (skips API call if already coordinates)
    coords_a = _geocode(location_a)
    coords_b = _geocode(location_b)
    
    # Get route
    AgentLogger.routing_calculating()
    route_url = f"{GRAPHHOPPER_BASE_URL}/route"
    
    AgentLogger.api_call("GraphHopper Routing", route_url, payload_size=0)
    
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
    
    paths = route_data.get("paths", [])
    if not paths:
        raise ValueError(f"No route found between ({coords_a['lat']},{coords_a['lng']}) and ({coords_b['lat']},{coords_b['lng']})")
    
    path = paths[0]
    
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
