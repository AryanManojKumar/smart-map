# routing_node — Turn-by-turn navigation

## Purpose
Compute a driving/biking/walking route between two SPECIFIC locations using GraphHopper.

## When to use
- User provides a SPECIFIC, NAMED destination (e.g., "take me to Apollo Hospital Ahmedabad", "Delhi to Mumbai")
- User references a POI from a previous search result by name
- User wants to re-route with different vehicle/preferences

## When NOT to use
- Destination is a GENERIC CATEGORY ("nearest hospital", "gas stations nearby") — use **search_node** instead
- User is asking about an already-computed route — use **route_question_node**

## Inputs
- `location_a`: Starting point (GPS coords or place name). Empty = user's current GPS.
- `location_b`: Destination (GPS coords or place name). MUST be specific.
- `vehicle`: "car" (default), "bike", or "foot"
- `avoid`: Optional list — "highways", "tolls", "ferries"

## Tools
- `search_locations` — Geocode place names to coordinates (via GraphHopper)
- `routing_engine` — Compute optimal route (via GraphHopper)

## Behavior
1. Geocodes location_a and location_b if not already coordinates
2. If geocoding returns ambiguous results → sets `pending_candidates` and exits (disambiguation_node handles next turn)
3. If both locations resolved → computes route and returns route_data with polyline, distance, time, turn-by-turn instructions
4. Also computes alternative routes when available

## Output state
- `route_data`: Full route object (distance_km, time_minutes, polyline, instructions)
- `route_context`: Pre-built text document for route Q&A
- `alternative_routes`: Grey alternative routes for the map

## Common failure modes
- Vague destination like "hospital" returns global geocoding results — supervisor should route to search_node instead
- Very long routes (>2000 km) may timeout — GraphHopper has a 30s limit
