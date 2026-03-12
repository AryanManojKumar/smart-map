# disambiguation_node — Smart location selection

## Purpose
Help the user choose from a list of candidate locations when a search or geocoding query returned multiple results. Uses GPT-5-2 to interpret natural language selections.

## When to use
- `pending_candidates` exists in state with a non-empty `candidates` list
- Automatically routed by the supervisor — no intent detection needed

## Candidate origins
Candidates can come from TWO sources:
1. **Geocoding** (routing_node): User searched for a place name that exists in multiple cities (e.g., "Chauhan Hospital" in 5 cities)
2. **POI search** (search_node): User searched for nearby POIs and wants to route to one of them

## User interaction patterns
GPT-5-2 interprets the user's message as one of four actions:

| Action | Trigger examples | Behavior |
|--------|-----------------|----------|
| **select** | "2", "the first one", "the one in Sanand" | Routes to selected location |
| **question** | "which is closest?", "is there one in Ahmedabad?" | Answers, keeps candidates |
| **re_search** | "search in Gujarat instead", "find one near me" | New search, updates candidates |
| **abandon** | "never mind", "take me to Delhi instead" | Clears candidates, returns to conversation |

## Distance sanity rules
- If user asks for "nearest" / "closest" / "pass wala" and ALL candidates are >50 km away, the geocoding failed to find local results
- In this case: action = "re_search", NOT "select" — suggest POI-based nearby search instead
- A "nearest hospital" should be within ~10 km, not 1000+ km

## Inputs
- `pending_candidates`: Dict with `candidates` list and `context` (location_a, location_b, ambiguous_field, origin)
- `location`: User's GPS for distance sanity checks
- `messages`: Conversation history for context

## Tools (used only for re_search)
- `search_locations` — Re-geocode with new query
- `routing_engine` — Compute route after selection

## Output state
- On select: `route_data`, clears `pending_candidates`
- On question: keeps `pending_candidates` (user hasn't chosen yet)
- On re_search: updates `pending_candidates` with new candidates
- On abandon: clears `pending_candidates`
