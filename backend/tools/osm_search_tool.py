import requests
from langchain_core.tools import tool
from typing import List, Dict
from backend.utils.logger import AgentLogger

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

@tool
def search_poi_along_route(polyline: List[List[float]], poi_type: str, radius_meters: int = 1000) -> List[Dict]:
    """Search for Points of Interest along a route using OpenStreetMap data.
    
    Args:
        polyline: List of [lat, lng] coordinates representing the route
        poi_type: Type of POI to search (e.g., 'fuel', 'charging_station', 'restaurant', 'atm', 'parking')
        radius_meters: Search radius around route in meters (default 1000m)
    
    Returns:
        List of POIs with name, type, coordinates, and distance info
    """
    
    AgentLogger.tool_call("search_poi_along_route", {
        "poi_type": poi_type,
        "radius_meters": radius_meters,
        "route_points": len(polyline)
    })
    
    # Map common POI types to OSM tags
    poi_mapping = {
        "fuel": "amenity=fuel",
        "gas_station": "amenity=fuel",
        "charging_station": "amenity=charging_station",
        "ev_charging": "amenity=charging_station",
        "restaurant": "amenity=restaurant",
        "cafe": "amenity=cafe",
        "atm": "amenity=atm",
        "parking": "amenity=parking",
        "hotel": "tourism=hotel",
        "hospital": "amenity=hospital"
    }
    
    osm_tag = poi_mapping.get(poi_type.lower(), f"amenity={poi_type}")
    
    # Sample points along route (every 10th point to reduce query size)
    sample_points = polyline[::10] if len(polyline) > 10 else polyline
    
    # Build Overpass query
    query_parts = []
    for lat, lng in sample_points:
        query_parts.append(f"  node[{osm_tag}](around:{radius_meters},{lat},{lng});")
    
    overpass_query = f"""
    [out:json][timeout:25];
    (
    {''.join(query_parts)}
    );
    out body;
    """
    
    response = requests.post(OVERPASS_URL, data={"data": overpass_query})
    response.raise_for_status()
    data = response.json()
    
    # Process results
    pois = []
    seen_ids = set()
    
    for element in data.get("elements", []):
        if element["id"] in seen_ids:
            continue
        seen_ids.add(element["id"])
        
        poi = {
            "name": element.get("tags", {}).get("name", "Unnamed"),
            "type": poi_type,
            "lat": element["lat"],
            "lng": element["lon"],
            "tags": element.get("tags", {})
        }
        pois.append(poi)
    
    result = pois[:20]  # Limit to 20 results
    AgentLogger.tool_result("search_poi_along_route", result)
    
    return result


@tool
def search_poi_nearby(lat: float, lng: float, poi_type: str, radius_meters: int = 5000) -> List[Dict]:
    """Search for Points of Interest near a specific location using OpenStreetMap data.
    
    Args:
        lat: Latitude of search center
        lng: Longitude of search center
        poi_type: Type of POI to search (e.g., 'fuel', 'charging_station', 'restaurant')
        radius_meters: Search radius in meters (default 5000m)
    
    Returns:
        List of nearby POIs with name, type, coordinates, and distance
    """
    
    AgentLogger.tool_call("search_poi_nearby", {
        "location": f"{lat:.4f}, {lng:.4f}",
        "poi_type": poi_type,
        "radius_meters": radius_meters
    })
    
    poi_mapping = {
        "fuel": "amenity=fuel",
        "gas_station": "amenity=fuel",
        "charging_station": "amenity=charging_station",
        "ev_charging": "amenity=charging_station",
        "restaurant": "amenity=restaurant",
        "cafe": "amenity=cafe",
        "atm": "amenity=atm",
        "parking": "amenity=parking",
        "hotel": "tourism=hotel",
        "hospital": "amenity=hospital"
    }
    
    osm_tag = poi_mapping.get(poi_type.lower(), f"amenity={poi_type}")
    
    overpass_query = f"""
    [out:json][timeout:25];
    (
      node[{osm_tag}](around:{radius_meters},{lat},{lng});
      way[{osm_tag}](around:{radius_meters},{lat},{lng});
    );
    out center body;
    """
    
    response = requests.post(OVERPASS_URL, data={"data": overpass_query})
    response.raise_for_status()
    data = response.json()
    
    pois = []
    for element in data.get("elements", []):
        # Get coordinates (handle both nodes and ways)
        if element["type"] == "node":
            poi_lat, poi_lng = element["lat"], element["lon"]
        elif element["type"] == "way" and "center" in element:
            poi_lat, poi_lng = element["center"]["lat"], element["center"]["lon"]
        else:
            continue
        
        # Calculate distance
        distance_km = _haversine_distance(lat, lng, poi_lat, poi_lng)
        
        poi = {
            "name": element.get("tags", {}).get("name", "Unnamed"),
            "type": poi_type,
            "lat": poi_lat,
            "lng": poi_lng,
            "distance_km": round(distance_km, 2),
            "tags": element.get("tags", {})
        }
        pois.append(poi)
    
    # Sort by distance
    pois.sort(key=lambda x: x["distance_km"])
    result = pois[:10]  # Return top 10 closest
    
    AgentLogger.tool_result("search_poi_nearby", result)
    
    return result


def _haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance between two points using Haversine formula."""
    from math import radians, sin, cos, sqrt, atan2
    
    R = 6371  # Earth radius in km
    
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return R * c
