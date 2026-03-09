"""
Location Search Tool — Smart location disambiguation.

Searches for locations and determines whether disambiguation is needed
based on how different the results actually are (not just result count).
"""

from langchain_core.tools import tool
from typing import List, Dict, Optional
import requests
from geopy.distance import geodesic
from backend.config import GRAPHHOPPER_API_KEY
from backend.utils.logger import AgentLogger


# ── Disambiguation Thresholds ─────────────────
# These control when disambiguation is triggered

# If the top results are all within this distance of each other (km),
# they're probably the same place — don't disambiguate
SAME_PLACE_RADIUS_KM = 5.0

# Types of places that are inherently ambiguous (chains, generic names)
AMBIGUOUS_TYPES = {"restaurant", "fast_food", "cafe", "fuel", "bank", "atm",
                   "pharmacy", "supermarket", "hotel", "parking"}


def _needs_disambiguation(query: str, locations: List[Dict]) -> bool:
    """
    Smart disambiguation check — only trigger when results are genuinely different.
    
    Rules:
    1. Single result → never disambiguate
    2. All results cluster within SAME_PLACE_RADIUS_KM → same place, don't disambiguate
    3. Results are a known ambiguous type (chain stores, etc.) → disambiguate
    4. Results span >SAME_PLACE_RADIUS_KM → disambiguate
    """
    if len(locations) <= 1:
        return False
    
    # Check if all results are geographically close (same place, different entries)
    first_loc = locations[0]["coordinates"]
    all_close = True
    
    for loc in locations[1:]:
        dist = geodesic(
            (first_loc["lat"], first_loc["lng"]),
            (loc["coordinates"]["lat"], loc["coordinates"]["lng"])
        ).kilometers
        if dist > SAME_PLACE_RADIUS_KM:
            all_close = False
            break
    
    if all_close:
        # All results are in the same area — just use the first one
        AgentLogger.info(f"All {len(locations)} results within {SAME_PLACE_RADIUS_KM}km — treating as same place")
        return False
    
    # Check if results are a known ambiguous type (chain/franchise)
    first_type = locations[0].get("type", "")
    if first_type in AMBIGUOUS_TYPES:
        AgentLogger.info(f"Ambiguous type detected: '{first_type}' — disambiguation needed")
        return True
    
    # Results are spread out — disambiguate
    AgentLogger.info(f"Results spread across different locations — disambiguation needed")
    return True


@tool
def search_locations(
    query: str,
    user_location: Optional[Dict[str, float]] = None,
    limit: int = 5
) -> Dict:
    """
    Search for locations by name or address and return multiple candidates.
    Uses smart disambiguation — only asks user to choose when results are genuinely different.
    
    Args:
        query: Location name or address to search for
        user_location: Optional dict with 'lat' and 'lng' keys for distance calculation
        limit: Maximum number of results to return (default 5)
    
    Returns:
        Dict with found, count, needs_disambiguation, locations, message
    """
    
    AgentLogger.tool_call("search_locations", {"query": query, "limit": limit})
    
    try:
        url = "https://graphhopper.com/api/1/geocode"
        
        params = {
            "q": query,
            "limit": limit,
            "key": GRAPHHOPPER_API_KEY
        }
        
        if user_location:
            params["point"] = f"{user_location['lat']},{user_location['lng']}"
        
        AgentLogger.api_call("GraphHopper Geocoding", url, payload_size=len(query))
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        AgentLogger.api_response("GraphHopper Geocoding", response.status_code,
                                  f"{len(data.get('hits', []))} hits for '{query}'")
        
        if not data.get("hits"):
            AgentLogger.info(f"No results found for '{query}'")
            return {
                "found": False,
                "count": 0,
                "needs_disambiguation": False,
                "locations": [],
                "message": f"No locations found for '{query}'"
            }
        
        # Process results
        locations = []
        for idx, hit in enumerate(data["hits"], 1):
            location = {
                "id": idx,
                "name": hit.get("name", query),
                "address": format_address(hit),
                "coordinates": {
                    "lat": hit["point"]["lat"],
                    "lng": hit["point"]["lng"]
                },
                "type": hit.get("osm_value", "location"),
                "country": hit.get("country", ""),
                "city": hit.get("city", ""),
                "state": hit.get("state", "")
            }
            
            if user_location:
                distance_km = geodesic(
                    (user_location["lat"], user_location["lng"]),
                    (location["coordinates"]["lat"], location["coordinates"]["lng"])
                ).kilometers
                location["distance_km"] = round(distance_km, 2)
                location["distance_text"] = format_distance(distance_km)
            
            locations.append(location)
        
        # Sort by distance if available
        if user_location:
            locations.sort(key=lambda x: x.get("distance_km", float('inf')))
        
        # IMPORTANT: Reassign IDs AFTER sorting so ID always matches position
        for idx, loc in enumerate(locations, 1):
            loc["id"] = idx
        
        # Smart disambiguation check
        disambiguate = _needs_disambiguation(query, locations)
        
        AgentLogger.tool_result("search_locations", {
            "found": True,
            "count": len(locations),
            "needs_disambiguation": disambiguate,
            "top_result": f"{locations[0]['name']} ({locations[0]['address']})"
        })
        
        return {
            "found": True,
            "count": len(locations),
            "needs_disambiguation": disambiguate,
            "locations": locations,
            "message": f"Found {len(locations)} location(s) for '{query}'"
        }
        
    except requests.exceptions.RequestException as e:
        AgentLogger.error(f"Search request failed: {str(e)}")
        return {
            "found": False, "count": 0, "needs_disambiguation": False,
            "locations": [], "error": f"Search failed: {str(e)}"
        }
    except Exception as e:
        AgentLogger.error(f"Search error: {str(e)}")
        return {
            "found": False, "count": 0, "needs_disambiguation": False,
            "locations": [], "error": f"Unexpected error: {str(e)}"
        }


def format_address(hit: Dict) -> str:
    """Format address from geocoding result."""
    parts = []
    if hit.get("street"):
        parts.append(hit["street"])
    elif hit.get("name"):
        parts.append(hit["name"])
    if hit.get("city"):
        parts.append(hit["city"])
    if hit.get("state"):
        parts.append(hit["state"])
    if hit.get("country"):
        parts.append(hit["country"])
    return ", ".join(parts) if parts else "Address not available"


def format_distance(distance_km: float) -> str:
    """Format distance in human-readable form."""
    if distance_km < 1:
        return f"{int(distance_km * 1000)} meters away"
    elif distance_km < 10:
        return f"{distance_km:.1f} km away"
    else:
        return f"{int(distance_km)} km away"
