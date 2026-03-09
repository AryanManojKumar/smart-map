"""
GraphHopper Routing Tool — geocodes locations and computes routes.

Supports alternative routes (up to 3 paths) and handles both
address strings and raw coordinate strings (lat,lng).
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
    """
    coords = _parse_coordinates(location)
    if coords:
        AgentLogger.info(f"Skipping geocode — already coordinates: ({coords['lat']:.4f}, {coords['lng']:.4f})")
        return coords
    
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


def _parse_path(path, coords_a, coords_b, location_a, location_b):
    """Parse a single GraphHopper path into structured route data."""
    polyline = [[point[1], point[0]] for point in path["points"]["coordinates"]]
    
    detailed_instructions = []
    for instr in path.get("instructions", []):
        detailed_instructions.append({
            "text": instr.get("text", ""),
            "street_name": instr.get("street_name", ""),
            "sign": instr.get("sign", 0),
            "distance_m": round(instr.get("distance", 0), 1),
            "time_ms": instr.get("time", 0),
            "interval": instr.get("interval", []),
        })
    
    road_details = {}
    for detail_key in ["road_class", "street_name", "lanes", "max_speed", "surface", "country"]:
        raw = path.get("details", {}).get(detail_key, [])
        road_details[detail_key] = raw
    
    return {
        "distance_km": round(path["distance"] / 1000, 2),
        "time_minutes": round(path["time"] / 60000, 2),
        "instructions": [instr["text"] for instr in path.get("instructions", [])],
        "detailed_instructions": detailed_instructions,
        "road_details": road_details,
        "polyline": polyline,
        "start_point": {"lat": coords_a["lat"], "lng": coords_a["lng"]},
        "end_point": {"lat": coords_b["lat"], "lng": coords_b["lng"]},
        "from": location_a,
        "to": location_b,
    }


@tool
def get_route(location_a: str, location_b: str, vehicle: str = "car") -> dict:
    """Get route directions between two locations using GraphHopper API.
    
    Returns the primary (fastest) route plus up to 2 alternative routes.
    
    Args:
        location_a: Starting location (address or coordinates like "28.6,77.2")
        location_b: Destination location (address or coordinates)
        vehicle: Vehicle type (car, bike, foot)
    
    Returns:
        Dictionary with primary route data and alternative_routes list.
    """
    
    AgentLogger.routing_start(location_a, location_b)
    
    coords_a = _geocode(location_a)
    coords_b = _geocode(location_b)
    
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
            "details": ["road_class", "street_name", "lanes", "max_speed", "surface", "country"],
            "alternative_route.max_paths": 3,
            "alternative_route.max_weight_factor": 2.5,
            "alternative_route.max_share_factor": 0.95,
            "key": GRAPHHOPPER_API_KEY,
        },
    )
    route_response.raise_for_status()
    route_data = route_response.json()
    
    paths = route_data.get("paths", [])
    if not paths:
        raise ValueError(f"No route found between ({coords_a['lat']},{coords_a['lng']}) and ({coords_b['lat']},{coords_b['lng']})")
    
    # Primary route (fastest)
    primary = _parse_path(paths[0], coords_a, coords_b, location_a, location_b)
    
    # Alternative routes
    alternatives = []
    for i, path in enumerate(paths[1:], 2):
        alt = _parse_path(path, coords_a, coords_b, location_a, location_b)
        alt["route_label"] = f"Route {i}"
        # Calculate time difference from primary
        time_diff = alt["time_minutes"] - primary["time_minutes"]
        alt["time_diff_minutes"] = round(time_diff, 1)
        alternatives.append(alt)
    
    if alternatives:
        AgentLogger.info(f"Found {len(alternatives)} alternative route(s)")
        for i, alt in enumerate(alternatives):
            sign = "+" if alt["time_diff_minutes"] >= 0 else ""
            AgentLogger.info(f"  Alt {i+1}: {alt['distance_km']} km, {sign}{alt['time_diff_minutes']} min vs primary")
    
    # Add alternatives to primary result
    primary["alternative_routes"] = alternatives
    
    AgentLogger.routing_complete(primary)
    AgentLogger.separator()
    
    return primary
