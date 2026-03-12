"""
Waze Traffic Tool — Fetches real-time alerts and jams from the Waze API.

Uses the OpenWebNinja Waze endpoint to get traffic incidents within
a geographic bounding box.
"""

import requests
from backend.config import WAZE_API_KEY, WAZE_BASE_URL
from backend.utils.logger import AgentLogger


def get_waze_alerts_and_jams(
    bottom_left: str,
    top_right: str,
    max_alerts: int = 10,
    max_jams: int = 10,
) -> dict:
    """
    Fetch real-time alerts and jams from Waze for a bounding box.

    Args:
        bottom_left: "lat,lng" of the SW corner
        top_right:   "lat,lng" of the NE corner
        max_alerts:  max alerts to return (default 10)
        max_jams:    max jams to return (default 10)

    Returns:
        dict with "alerts" and "jams" lists, or an error dict.
    """
    if not WAZE_API_KEY:
        AgentLogger.error("WAZE_API_KEY is not configured")
        return {"alerts": [], "jams": [], "error": "Waze API key not configured"}

    url = f"{WAZE_BASE_URL}/alerts-and-jams"
    params = {
        "bottom_left": bottom_left,
        "top_right": top_right,
        "max_alerts": max_alerts,
        "max_jams": max_jams,
    }
    headers = {"x-api-key": WAZE_API_KEY}

    AgentLogger.api_call("Waze Traffic", url, payload_size=0)

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        AgentLogger.api_response("Waze Traffic", response.status_code)

        raw_alerts = data.get("data", {}).get("alerts", [])
        raw_jams = data.get("data", {}).get("jams", [])

        # Normalize alerts
        alerts = []
        for a in raw_alerts:
            alerts.append({
                "alert_id": a.get("alert_id"),
                "type": a.get("type", "UNKNOWN"),
                "subtype": a.get("subtype"),
                "description": a.get("description", ""),
                "latitude": a.get("latitude"),
                "longitude": a.get("longitude"),
                "street": a.get("street", ""),
                "city": a.get("city", ""),
                "publish_datetime_utc": a.get("publish_datetime_utc"),
            })

        # Normalize jams
        jams = []
        for j in raw_jams:
            line = j.get("line", [])
            line_coords = [[pt.get("y"), pt.get("x")] for pt in line] if line else []
            jams.append({
                "id": j.get("id"),
                "level": j.get("level", 0),
                "speed_kmh": round(j.get("speed", 0) * 3.6, 1) if j.get("speed") else 0,
                "length": j.get("length", 0),
                "description": j.get("street", ""),
                "street": j.get("street", ""),
                "line": line_coords,
            })

        AgentLogger.info(f"Waze: {len(alerts)} alerts, {len(jams)} jams in area")
        return {"alerts": alerts, "jams": jams}

    except requests.exceptions.Timeout:
        AgentLogger.error("Waze API timeout")
        return {"alerts": [], "jams": [], "error": "Waze API timeout"}
    except requests.exceptions.RequestException as e:
        AgentLogger.error(f"Waze API error: {e}")
        return {"alerts": [], "jams": [], "error": str(e)}
    except Exception as e:
        AgentLogger.error(f"Waze tool error: {e}")
        return {"alerts": [], "jams": [], "error": str(e)}
