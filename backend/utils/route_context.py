"""
Route Context Builder — builds a structured text document from enriched route data.

The output is designed to be injected into an LLM prompt so the agent
can answer conversational questions about an active route (highway count,
lane info, turns, surface types, etc.) purely from the data.
"""

from collections import defaultdict

# GraphHopper "sign" codes → human-readable turn types
_SIGN_MAP = {
    -98: "U-turn",
    -8: "U-turn left",
    -7: "Keep left",
    -6: "Leave roundabout",
    -3: "Turn sharp left",
    -2: "Turn left",
    -1: "Turn slight left",
    0: "Continue",
    1: "Turn slight right",
    2: "Turn right",
    3: "Turn sharp right",
    4: "Finish",
    5: "Reached via",
    6: "Use roundabout",
    7: "Keep right",
    8: "U-turn right",
}


def _sign_to_text(sign: int) -> str:
    return _SIGN_MAP.get(sign, f"Maneuver ({sign})")


def _format_duration(minutes: float) -> str:
    """Format minutes into a human-readable duration string."""
    if minutes < 60:
        return f"{int(minutes)} min"
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    if mins == 0:
        return f"{hours}h"
    return f"{hours}h {mins}min"


def _format_distance(meters: float) -> str:
    """Format meters into km or m."""
    if meters >= 1000:
        return f"{meters / 1000:.1f} km"
    return f"{int(meters)} m"


def _classify_road(road_class: str) -> str:
    """Map GraphHopper road_class to a friendlier category."""
    mapping = {
        "motorway": "Motorway / Expressway",
        "trunk": "National Highway / Trunk Road",
        "primary": "Primary Road / State Highway",
        "secondary": "Secondary Road",
        "tertiary": "Tertiary Road",
        "residential": "Residential Road",
        "service": "Service Road",
        "unclassified": "Unclassified Road",
        "track": "Track / Unpaved",
        "living_street": "Living Street",
    }
    return mapping.get(road_class, road_class.replace("_", " ").title() if road_class else "Unknown")


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def build_route_context(route_data: dict) -> str:
    """
    Build a structured text document from enriched route data.
    
    Args:
        route_data: Dict returned by the enriched GraphHopper tool,
                    containing detailed_instructions and road_details.
    
    Returns:
        A multi-section text document ready to be injected into an LLM prompt.
    """
    sections = []
    
    # ── ROUTE SUMMARY ──
    sections.append("ROUTE SUMMARY")
    sections.append(f"From: {route_data.get('from', 'Unknown')}")
    sections.append(f"To: {route_data.get('to', 'Unknown')}")
    sections.append(f"Total Distance: {route_data.get('distance_km', '?')} km")
    sections.append(f"Estimated Duration: {_format_duration(route_data.get('time_minutes', 0))}")
    sections.append("")
    
    # ── TURN-BY-TURN DIRECTIONS ──
    detailed = route_data.get("detailed_instructions", [])
    if detailed:
        sections.append(f"TURN-BY-TURN DIRECTIONS ({len(detailed)} steps)")
        for i, step in enumerate(detailed, 1):
            turn = _sign_to_text(step.get("sign", 0))
            text = step.get("text", "")
            street = step.get("street_name", "")
            dist = _format_distance(step.get("distance_m", 0))
            time_min = step.get("time_ms", 0) / 60000
            time_str = _format_duration(time_min)
            
            street_info = f" [{street}]" if street and street != text else ""
            sections.append(f"  {i}. [{turn}] {text}{street_info} ({dist}, {time_str})")
        sections.append("")
    
    # ── ROAD STATISTICS ──
    road_details = route_data.get("road_details", {})
    polyline = route_data.get("polyline", [])
    total_points = len(polyline)
    
    if road_details and total_points > 0:
        sections.append("ROAD STATISTICS")
        
        # Road class breakdown
        road_classes = road_details.get("road_class", [])
        if road_classes:
            class_distances = defaultdict(float)
            class_names = defaultdict(set)
            street_names_detail = road_details.get("street_name", [])
            
            for segment in road_classes:
                if len(segment) >= 3:
                    from_idx, to_idx, rc = segment[0], segment[1], segment[2]
                    # Approximate distance by fraction of total route
                    fraction = (to_idx - from_idx) / max(total_points - 1, 1)
                    seg_dist = fraction * route_data.get("distance_km", 0)
                    class_distances[rc] += seg_dist
                    
                    # Collect street names for this class
                    for sn_seg in street_names_detail:
                        if len(sn_seg) >= 3:
                            sn_from, sn_to, name = sn_seg[0], sn_seg[1], sn_seg[2]
                            # Check overlap
                            if sn_from < to_idx and sn_to > from_idx and name:
                                class_names[rc].add(name)
            
            sections.append("  Road Class Breakdown:")
            for rc, dist in sorted(class_distances.items(), key=lambda x: -x[1]):
                friendly = _classify_road(rc)
                names = class_names.get(rc, set())
                names_str = ""
                if names:
                    top_names = sorted(names)[:8]
                    names_str = f" — includes: {', '.join(top_names)}"
                    if len(names) > 8:
                        names_str += f" (+{len(names)-8} more)"
                sections.append(f"    • {friendly}: {dist:.1f} km{names_str}")
            sections.append("")
        
        # Lanes breakdown
        lanes_data = road_details.get("lanes", [])
        if lanes_data:
            lane_distances = defaultdict(float)
            for segment in lanes_data:
                if len(segment) >= 3:
                    from_idx, to_idx, lanes = segment[0], segment[1], segment[2]
                    fraction = (to_idx - from_idx) / max(total_points - 1, 1)
                    seg_dist = fraction * route_data.get("distance_km", 0)
                    lane_distances[lanes] += seg_dist
            
            sections.append("  Lane Breakdown:")
            for lanes, dist in sorted(lane_distances.items(), key=lambda x: x[0] if isinstance(x[0], int) else 0):
                sections.append(f"    • {lanes}-lane: {dist:.1f} km")
            sections.append("")
        
        # Speed limits
        speed_data = road_details.get("max_speed", [])
        if speed_data:
            speed_distances = defaultdict(float)
            for segment in speed_data:
                if len(segment) >= 3:
                    from_idx, to_idx, speed = segment[0], segment[1], segment[2]
                    fraction = (to_idx - from_idx) / max(total_points - 1, 1)
                    seg_dist = fraction * route_data.get("distance_km", 0)
                    speed_distances[speed] += seg_dist
            
            sections.append("  Speed Limit Breakdown:")
            for speed, dist in sorted(speed_distances.items(), key=lambda x: x[0] if isinstance(x[0], (int, float)) else 0):
                label = f"{speed} km/h" if isinstance(speed, (int, float)) and speed > 0 else "Unmarked"
                sections.append(f"    • {label}: {dist:.1f} km")
            sections.append("")
        
        # Surface types
        surface_data = road_details.get("surface", [])
        if surface_data:
            surface_distances = defaultdict(float)
            for segment in surface_data:
                if len(segment) >= 3:
                    from_idx, to_idx, surface = segment[0], segment[1], segment[2]
                    fraction = (to_idx - from_idx) / max(total_points - 1, 1)
                    seg_dist = fraction * route_data.get("distance_km", 0)
                    surface_distances[surface] += seg_dist
            
            sections.append("  Surface Breakdown:")
            for surface, dist in sorted(surface_distances.items(), key=lambda x: -x[1]):
                label = surface.replace("_", " ").title() if surface else "Unknown"
                sections.append(f"    • {label}: {dist:.1f} km")
            sections.append("")
        
        # Countries
        country_data = road_details.get("country", [])
        if country_data:
            country_distances = defaultdict(float)
            for segment in country_data:
                if len(segment) >= 3:
                    from_idx, to_idx, country = segment[0], segment[1], segment[2]
                    fraction = (to_idx - from_idx) / max(total_points - 1, 1)
                    seg_dist = fraction * route_data.get("distance_km", 0)
                    country_distances[country] += seg_dist
            
            if len(country_distances) > 1:
                sections.append("  Countries Traversed:")
                for country, dist in sorted(country_distances.items(), key=lambda x: -x[1]):
                    sections.append(f"    • {country}: {dist:.1f} km")
                sections.append("")
    
    # ── NAMED ROADS LIST ──
    street_names = road_details.get("street_name", []) if road_details else []
    if street_names:
        name_distances = defaultdict(float)
        for segment in street_names:
            if len(segment) >= 3 and segment[2]:
                from_idx, to_idx, name = segment[0], segment[1], segment[2]
                fraction = (to_idx - from_idx) / max(total_points - 1, 1)
                seg_dist = fraction * route_data.get("distance_km", 0)
                name_distances[name] += seg_dist
        
        if name_distances:
            # Show top roads by distance
            sorted_roads = sorted(name_distances.items(), key=lambda x: -x[1])
            sections.append(f"MAJOR ROADS ON ROUTE (top {min(15, len(sorted_roads))} by distance)")
            for name, dist in sorted_roads[:15]:
                sections.append(f"  • {name}: {dist:.1f} km")
            sections.append("")
    
    return "\n".join(sections)


def build_route_stats(route_data: dict) -> dict:
    """
    Build a structured stats dict from enriched route data.
    Useful for programmatic access to route statistics.
    """
    stats = {
        "distance_km": route_data.get("distance_km", 0),
        "time_minutes": route_data.get("time_minutes", 0),
        "num_steps": len(route_data.get("detailed_instructions", [])),
        "road_classes": {},
        "lanes": {},
        "surfaces": {},
        "named_roads": {},
    }
    
    road_details = route_data.get("road_details", {})
    total_points = len(route_data.get("polyline", []))
    
    if not road_details or total_points == 0:
        return stats
    
    total_dist = route_data.get("distance_km", 0)
    
    for key, state_key in [("road_class", "road_classes"), ("lanes", "lanes"), 
                            ("surface", "surfaces"), ("street_name", "named_roads")]:
        data = road_details.get(key, [])
        breakdown = defaultdict(float)
        for segment in data:
            if len(segment) >= 3 and segment[2]:
                fraction = (segment[1] - segment[0]) / max(total_points - 1, 1)
                breakdown[segment[2]] += fraction * total_dist
        stats[state_key] = {k: round(v, 1) for k, v in sorted(breakdown.items(), key=lambda x: -x[1])}
    
    return stats
