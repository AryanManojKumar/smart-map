# search_node — POI discovery

## Purpose
Find Points of Interest (hospitals, fuel stations, restaurants, ATMs, etc.) near the user or along their active route using OpenStreetMap/Overpass.

## When to use
- User wants to find places by CATEGORY: "nearest hospital", "petrol pumps nearby", "restaurants near me"
- User uses proximity words: "nearest", "closest", "nearby", "near me", "pass mein", "sabse pass"
- "Take me to the nearest X" — this is SEARCH first (find the nearest X), routing comes after
- User wants POIs along an active route: "gas stations on the way", "raste mein koi hotel?"

## When NOT to use
- User names a SPECIFIC place: "take me to Apollo Hospital" — use **routing_node**
- User asks about an active route: "how many tolls?" — use **route_question_node**

## Inputs
- `poi_type`: Standardized type string extracted by the supervisor
- `location`: User's current GPS coordinates
- `route_data`: Active route polyline (if searching along a route)

## POI type mapping (user language → poi_type)
| User says | poi_type |
|-----------|----------|
| hospital, clinic, medical | hospital |
| petrol pump, gas station, fuel | fuel |
| EV charger, charging | charging_station |
| restaurant, food, khana | restaurant |
| cafe, coffee | cafe |
| ATM, cash | atm |
| parking | parking |
| hotel, lodge, stay | hotel |
| pharmacy, medical store, dawai | pharmacy |
| supermarket, grocery | supermarket |

## Tools
- `search_poi_nearby` — OSM Overpass query around a GPS point (default 5 km radius)
- `search_poi_along_route` — OSM Overpass query along a route polyline

## Behavior
1. Sub-agent (GPT-5-2 with tool-calling) decides which tool to use based on context
2. Returns up to 10 POIs sorted by distance with name, coordinates, distance_km
3. Results are stored in `search_results` for map markers AND for follow-up routing

## Output state
- `search_results`: List of POI dicts with lat, lng, name, distance_km — used for map markers
- After search results exist, user can say "take me to the first one" or "number 3" and disambiguation_node will handle selection

## Common failure modes
- Overpass API can timeout (504) — the agent falls back to formatting raw tool results
- LLM summary call may fail — fallback formatter produces a clean numbered list anyway
