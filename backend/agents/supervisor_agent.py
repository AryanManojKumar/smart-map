"""
Supervisor Agent — Stateful multi-node LangGraph agent.

Uses PostgreSQL checkpointing to persist full state (messages, route data,
disambiguation candidates) between conversation turns via thread_id.

LLM Strategy:
  - Gemini 2.5 Flash: Fast intent detection (router)
  - Claude Sonnet 4.5: Smart disambiguation + conversation (needs reasoning)

Graph structure:
  router → routing_node | search_node | conversation_node | disambiguation_node → END
"""

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from backend.models.state import SupervisorState
from backend.agents.routing_engine import routing_engine
from backend.agents.search_agent import run_search_agent
from backend.tools.location_search_tool import search_locations
from backend.config import KIE_API_KEY, KIE_BASE_URL
from backend.utils.logger import AgentLogger
from typing import Optional
from backend.utils.route_context import build_route_context
import json
import requests
import re


# ──────────────────────────────────────────────
# LLM Helpers
# ──────────────────────────────────────────────

def call_kie_api(messages, purpose: str = ""):
    """Call Gemini 2.5 Flash via Kie API — fast, for intent detection."""
    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    formatted_messages = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            role = "system"
        elif isinstance(msg, AIMessage):
            role = "assistant"
        else:
            role = "user"
        formatted_messages.append({"role": role, "content": msg.content})
    
    payload = {
        "model": "gemini-2.5-flash",
        "messages": formatted_messages,
        "temperature": 0,
        "stream": False
    }
    
    total_chars = sum(len(m["content"]) for m in formatted_messages)
    AgentLogger.api_call("Kie AI (Gemini 2.5 Flash)", f"{KIE_BASE_URL}/gemini-2.5-flash/v1/chat/completions",
                         model="gemini-2.5-flash", payload_size=total_chars)
    
    response = requests.post(
        f"{KIE_BASE_URL}/gemini-2.5-flash/v1/chat/completions",
        headers=headers, json=payload, timeout=60
    )
    data = response.json()
    
    if "choices" in data and data["choices"]:
        content = data["choices"][0].get("message", {}).get("content")
        if content:
            AgentLogger.api_response("Gemini 2.5 Flash", response.status_code, content[:200])
            return content
    if "data" in data and data["data"]:
        return str(data["data"])
    
    AgentLogger.error(f"Gemini API error: {data.get('msg', 'unknown')}")
    raise Exception(f"Could not extract content. Keys: {list(data.keys())}")


def call_claude_api(messages, purpose: str = ""):
    """Call Claude Sonnet 4.5 via Kie API — smart, for reasoning & disambiguation."""
    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    formatted_messages = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            role = "system"
        elif isinstance(msg, AIMessage):
            role = "assistant"
        else:
            role = "user"
        # Claude API via Kie expects content as array of objects
        formatted_messages.append({
            "role": role,
            "content": [{"type": "text", "text": msg.content}]
        })
    
    payload = {
        "messages": formatted_messages,
        "stream": False,
        "include_thoughts": False,
        "reasoning_effort": "low"
    }
    
    total_chars = sum(len(msg.content) for msg in messages)
    AgentLogger.api_call("Kie AI (Claude Sonnet 4.5)", f"{KIE_BASE_URL}/claude-opus-4-5/v1/chat/completions",
                         model="claude-sonnet-4.5", payload_size=total_chars)
    
    response = requests.post(
        f"{KIE_BASE_URL}/claude-opus-4-5/v1/chat/completions",
        headers=headers, json=payload, timeout=90
    )
    data = response.json()
    
    if "choices" in data and data["choices"]:
        content = data["choices"][0].get("message", {}).get("content")
        if content:
            AgentLogger.api_response("Claude Sonnet 4.5", response.status_code, content[:200])
            return content
    if "data" in data and data["data"]:
        return str(data["data"])
    
    AgentLogger.error(f"Claude API error: {data.get('msg', 'unknown')}")
    raise Exception(f"Could not extract Claude response. Keys: {list(data.keys())}")


# ──────────────────────────────────────────────
# Utility Functions
# ──────────────────────────────────────────────

def _extract_pois_from_messages(messages) -> list:
    """Extract POI data from search agent ToolMessages for map markers."""
    from langchain_core.messages import ToolMessage
    pois = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            try:
                content = msg.content
                if isinstance(content, str):
                    data = json.loads(content)
                else:
                    data = content
                
                # Handle list of POIs directly
                if isinstance(data, list):
                    for poi in data:
                        if isinstance(poi, dict) and "lat" in poi and "lng" in poi:
                            pois.append({
                                "name": poi.get("name", "Unnamed"),
                                "type": poi.get("type", "poi"),
                                "lat": poi["lat"],
                                "lng": poi["lng"],
                                "distance_km": poi.get("distance_km")
                            })
                # Handle dict with pois key
                elif isinstance(data, dict) and "pois" in data:
                    for poi in data["pois"]:
                        if isinstance(poi, dict) and "lat" in poi and "lng" in poi:
                            pois.append({
                                "name": poi.get("name", "Unnamed"),
                                "type": poi.get("type", "poi"),
                                "lat": poi["lat"],
                                "lng": poi["lng"],
                                "distance_km": poi.get("distance_km")
                            })
            except (json.JSONDecodeError, TypeError, KeyError):
                pass
    return pois

def is_coordinates(location: str) -> bool:
    """Check if location string is GPS coordinates (lat,lng)."""
    try:
        parts = location.split(',')
        if len(parts) == 2:
            lat = float(parts[0].strip())
            lng = float(parts[1].strip())
            return -90 <= lat <= 90 and -180 <= lng <= 180
    except (ValueError, AttributeError):
        pass
    return False


def format_location_options(query: str, candidates: list) -> str:
    """Format location candidates as a user-friendly message."""
    response = f"I found {len(candidates)} locations for '{query}':\n\n"
    for candidate in candidates:
        response += f"{candidate['id']}. **{candidate['name']}**\n"
        response += f"   📍 {candidate['address']}\n"
        if candidate.get("distance_text"):
            response += f"   📏 {candidate['distance_text']}\n"
        response += "\n"
    response += "Which one would you like? You can reply with a number, name, or ask me anything about these options."
    return response


def format_candidates_for_llm(candidates: list) -> str:
    """Format candidates as structured text for the LLM to reason about."""
    lines = []
    for c in candidates:
        dist = f" ({c.get('distance_text', '')})" if c.get('distance_text') else ""
        lines.append(f"  {c['id']}. {c['name']} — {c['address']}{dist}")
        lines.append(f"     Coordinates: ({c['coordinates']['lat']}, {c['coordinates']['lng']})")
        if c.get('city'):
            lines.append(f"     City: {c['city']}")
        if c.get('state'):
            lines.append(f"     State: {c['state']}")
    return "\n".join(lines)


def format_conversation_history(messages) -> str:
    """Format recent message history as context for the LLM."""
    history_lines = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            history_lines.append(f"User: {msg.content}")
        elif isinstance(msg, AIMessage):
            content = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
            history_lines.append(f"Assistant: {content}")
    return "\n".join(history_lines) if history_lines else "(No prior conversation)"


# ──────────────────────────────────────────────
# Graph Nodes
# ──────────────────────────────────────────────

def router_node(state: SupervisorState):
    """
    Main routing node — determines which handler to invoke.
    Uses Gemini 2.5 Flash for fast intent detection.
    """
    AgentLogger.node_enter("router", f"Message: \"{state['messages'][-1].content[:80]}\"")
    
    messages = state["messages"]
    user_message = messages[-1].content
    pending_candidates = state.get("pending_candidates")
    
    # Show conversation context
    context_messages = messages[:-1]
    AgentLogger.conversation_context(context_messages)
    
    # If disambiguating, route directly — Claude will handle it smartly
    if pending_candidates and pending_candidates.get("candidates"):
        num = len(pending_candidates["candidates"])
        AgentLogger.node_route("router", "disambiguation_node", f"{num} pending candidates — Claude will interpret user response")
        return {"current_intent": "disambiguation"}
    
    # Build conversation context for intent detection
    history_messages = messages[-21:-1] if len(messages) > 1 else []
    history_text = format_conversation_history(history_messages)
    
    # Check if there's an active route for route_question detection
    has_route = bool(state.get("route_data"))
    
    route_hint = ""
    if has_route:
        route_hint = """\n4. If the user is asking about the CURRENT/ACTIVE route (e.g. "how many highways?", "list the turns", 
   "how many lanes?", "what roads are we taking?", "any tolls?", "total distance on NH?",
   "show me the directions", "what surface?", "which countries?"), set intent to "route_question".
   This is ONLY for questions about an already-computed route, NOT for requesting a new route."""
    
    intent_prompt = """You are a navigation assistant supervisor. Analyze the user's message and determine their intent.

Extract:
1. Intent: "routing", "search", "conversation"{route_question_option}
2. If routing: Extract location_a (start) and location_b (destination)
   - Leave location_a empty if user wants to start from current location
   - If user references a previous route context (e.g., "what about by bike?"), extract the same locations
3. If search: Extract poi_type (gas station, restaurant, etc.)

{active_route_note}Conversation history:
{history}

Current user message: "{message}"

Respond ONLY with valid JSON:
{{
    "intent": "routing" or "search" or "conversation"{route_question_json_option},
    "location_a": "start location or empty string",
    "location_b": "destination or empty string",
    "poi_type": "search type or empty string",
    "clarification_needed": false,
    "clarification_message": ""
}}""".format(
        route_question_option=' or "route_question"' if has_route else '',
        route_question_json_option=' or "route_question"' if has_route else '',
        active_route_note=f'NOTE: There is an ACTIVE ROUTE from {state.get("route_data", {}).get("from", "?")} to {state.get("route_data", {}).get("to", "?")}. If the user asks about this route, use intent "route_question".\n\n' if has_route else '',
        history=history_text,
        message=user_message
    )
    
    combined_prompt = intent_prompt
    AgentLogger.llm_prompt("Intent Detection (Gemini)", combined_prompt, num_context_messages=len(history_messages))
    
    try:
        intent_response = call_kie_api([HumanMessage(content=combined_prompt)], purpose="intent_detection")
        AgentLogger.llm_response("Intent Detection", intent_response)
        
        response_text = intent_response.strip()
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        
        if json_start >= 0 and json_end > json_start:
            intent_data = json.loads(response_text[json_start:json_end])
        else:
            raise json.JSONDecodeError("No JSON found", response_text, 0)
        
        AgentLogger.llm_parsed_intent(intent_data)
        intent = intent_data.get("intent", "conversation")
        
        if intent_data.get("clarification_needed"):
            AgentLogger.node_exit("router", "clarification")
            return {
                "messages": [AIMessage(content=intent_data["clarification_message"])],
                "current_intent": "clarification"
            }
        
        result = {"current_intent": intent}
        
        if intent == "routing":
            location_a = intent_data.get("location_a", "")
            location_b = intent_data.get("location_b", "")
            result["_routing_params"] = {"location_a": location_a, "location_b": location_b}
            AgentLogger.node_route("router", "routing_node", f"{location_a or '(GPS)'} → {location_b}")
        elif intent == "search":
            result["_search_params"] = {"poi_type": intent_data.get("poi_type", "")}
            AgentLogger.node_route("router", "search_node", f"POI: {intent_data.get('poi_type', '')}")
        elif intent == "route_question":
            AgentLogger.node_route("router", "route_question_node", "Route Q&A")
        else:
            AgentLogger.node_route("router", "conversation_node", "General conversation")
        
        AgentLogger.node_exit("router", intent)
        return result
    
    except json.JSONDecodeError as e:
        AgentLogger.error(f"Intent parse failed: {str(e)}")
        return {"current_intent": "conversation"}
    except Exception as e:
        AgentLogger.error(f"Router error: {str(e)}")
        return {
            "messages": [AIMessage(content="I'm here to help with navigation! Ask me for directions or to find places nearby.")],
            "current_intent": "error"
        }


def routing_node(state: SupervisorState):
    """Handle routing requests — geocode, disambiguate, or compute route."""
    AgentLogger.node_enter("routing_node")
    
    user_location = state.get("location")
    routing_params = state.get("_routing_params", {})
    location_a = routing_params.get("location_a", "")
    location_b = routing_params.get("location_b", "")
    
    if not location_a and user_location:
        location_a = f"{user_location['lat']},{user_location['lng']}"
        AgentLogger.info("Using user GPS as start location")
    
    if not location_a or not location_b:
        AgentLogger.node_exit("routing_node", "clarification")
        return {
            "messages": [AIMessage(content="I need both a starting location and destination. Could you provide both?")],
            "current_intent": "clarification"
        }
    
    AgentLogger.info(f"Route request: {location_a} → {location_b}")
    
    # Search location_a (if not coordinates)
    if not is_coordinates(location_a):
        AgentLogger.tool_call("search_locations", {"query": location_a, "limit": 5})
        search_result_a = search_locations.invoke({"query": location_a, "user_location": user_location, "limit": 5})
        AgentLogger.tool_result("search_locations", search_result_a)
        
        if search_result_a.get("needs_disambiguation"):
            candidates = search_result_a["locations"]
            AgentLogger.disambiguation_candidates(location_a, len(candidates), candidates)
            response = format_location_options(location_a, candidates)
            AgentLogger.node_exit("routing_node", "disambiguation")
            return {
                "messages": [AIMessage(content=response)],
                "current_intent": "disambiguation",
                "pending_candidates": {
                    "candidates": candidates,
                    "context": {"location_a": location_a, "location_b": location_b, "ambiguous_field": "location_a"}
                },
                "location_candidates": candidates
            }
        
        if search_result_a.get("found") and search_result_a["locations"]:
            loc_a = search_result_a["locations"][0]
            location_a = f"{loc_a['coordinates']['lat']},{loc_a['coordinates']['lng']}"
            AgentLogger.info(f"Resolved start → ({location_a})")
    
    # Search location_b
    AgentLogger.tool_call("search_locations", {"query": location_b, "limit": 5})
    search_result_b = search_locations.invoke({"query": location_b, "user_location": user_location, "limit": 5})
    AgentLogger.tool_result("search_locations", search_result_b)
    
    if search_result_b.get("needs_disambiguation"):
        candidates = search_result_b["locations"]
        AgentLogger.disambiguation_candidates(location_b, len(candidates), candidates)
        response = format_location_options(location_b, candidates)
        AgentLogger.node_exit("routing_node", "disambiguation")
        return {
            "messages": [AIMessage(content=response)],
            "current_intent": "disambiguation",
            "pending_candidates": {
                "candidates": candidates,
                "context": {"location_a": location_a, "location_b": location_b, "ambiguous_field": "location_b"}
            },
            "location_candidates": candidates
        }
    
    if search_result_b.get("found") and search_result_b["locations"]:
        loc_b = search_result_b["locations"][0]
        location_b = f"{loc_b['coordinates']['lat']},{loc_b['coordinates']['lng']}"
        AgentLogger.info(f"Resolved destination → ({location_b})")
    
    # Compute route (with alternatives)
    AgentLogger.tool_call("routing_engine", {"from": location_a, "to": location_b})
    try:
        route_data = routing_engine(location_a, location_b)
        
        # Extract alternatives before storing
        alternatives = route_data.pop("alternative_routes", [])
        
        AgentLogger.state_update("route_data", route_data)
        
        # Build route context for conversational Q&A
        route_context = build_route_context(route_data)
        AgentLogger.info(f"Built route context ({len(route_context)} chars)")
        
        # Build response mentioning alternatives
        response = f"I found a route from {route_data['from']} to {route_data['to']}! It's {route_data['distance_km']} km and will take about {route_data['time_minutes']} minutes."
        
        if alternatives:
            response += f"\n\n🗺️ I also found **{len(alternatives)} alternative route(s)** — shown in grey on the map. Click any grey route to switch to it!"
            for i, alt in enumerate(alternatives):
                sign = "+" if alt.get("time_diff_minutes", 0) >= 0 else ""
                response += f"\n  • Route {i+2}: {alt['distance_km']} km ({sign}{alt.get('time_diff_minutes', 0)} min)"
        
        response += "\n\n💡 You can ask me anything about this route — highway details, lane counts, turn-by-turn directions, road surfaces, and more!"
        
        AgentLogger.agent_response(response)
        AgentLogger.node_exit("routing_node", "routing")
        return {
            "messages": [AIMessage(content=response)],
            "route_data": route_data,
            "route_context": route_context,
            "alternative_routes": alternatives,
            "current_intent": "routing"
        }
    except Exception as e:
        AgentLogger.error(f"Routing failed: {str(e)}")
        return {
            "messages": [AIMessage(content="Sorry, I couldn't find a route. Please check the location names and try again.")],
            "current_intent": "error"
        }


def search_node(state: SupervisorState):
    """Handle POI search requests — extract POI markers for the map."""
    AgentLogger.node_enter("search_node")
    
    user_message = state["messages"][-1].content
    search_params = state.get("_search_params", {})
    poi_type = search_params.get("poi_type", "")
    route_data = state.get("route_data")
    location = state.get("location")
    
    AgentLogger.info(f"Searching for: {poi_type}")
    
    try:
        result = run_search_agent(user_message, route_data=route_data, location=location)
        agent_response = result["messages"][-1].content
        
        # Extract POI data from tool messages for map markers
        pois = _extract_pois_from_messages(result.get("messages", []))
        if pois:
            AgentLogger.info(f"Extracted {len(pois)} POIs for map markers")
        
        AgentLogger.agent_response(agent_response)
        AgentLogger.node_exit("search_node", "search")
        return {
            "messages": [AIMessage(content=agent_response)],
            "current_intent": "search",
            "search_results": pois
        }
    except Exception as e:
        AgentLogger.error(f"Search failed: {str(e)}")
        return {
            "messages": [AIMessage(content="Sorry, I couldn't complete the search. Please try again.")],
            "current_intent": "error"
        }


def conversation_node(state: SupervisorState):
    """Handle general conversation — uses Claude for quality responses."""
    AgentLogger.node_enter("conversation_node")
    
    messages = state["messages"]
    user_message = messages[-1].content
    context_messages = messages[-11:-1] if len(messages) > 1 else []
    history_text = format_conversation_history(context_messages)
    
    route_hint = ""
    if state.get("route_data"):
        rd = state["route_data"]
        route_hint = f"\n\nNote: There is an active route from {rd.get('from', '?')} to {rd.get('to', '?')} ({rd.get('distance_km', '?')} km). If the user asks about it, suggest they can ask questions about the route details."
    
    conversation_prompt = f"""You are a friendly navigation assistant named Nav AI.

Your capabilities:
- Find routes between any two locations worldwide
- Search for places like gas stations, restaurants, hotels, parking, etc.
- Provide navigation assistance and travel information
- Answer detailed questions about active routes (highways, lanes, turns, road types){route_hint}

Conversation history:
{history_text}

Current user message: {user_message}

Respond naturally. Be concise, helpful, and enthusiastic about navigation."""
    
    AgentLogger.llm_prompt("Conversation (Claude)", conversation_prompt, num_context_messages=len(context_messages))
    
    try:
        response_text = call_claude_api([HumanMessage(content=conversation_prompt)], purpose="conversation")
        AgentLogger.llm_response("Conversation", response_text)
        AgentLogger.agent_response(response_text)
        AgentLogger.node_exit("conversation_node", "conversation")
        return {
            "messages": [AIMessage(content=response_text)],
            "current_intent": "conversation"
        }
    except Exception as e:
        AgentLogger.error(f"Conversation error: {str(e)}")
        return {
            "messages": [AIMessage(content="I'm here to help with navigation! Ask me for directions or to find places nearby.")],
            "current_intent": "error"
        }


def route_question_node(state: SupervisorState):
    """
    Handle questions about the active route — uses Claude with the full
    route context document to provide data-backed answers.
    """
    AgentLogger.node_enter("route_question_node")
    
    messages = state["messages"]
    user_message = messages[-1].content
    route_context = state.get("route_context", "")
    route_data = state.get("route_data", {})
    
    # If no route context, rebuild it from route_data
    if not route_context and route_data:
        route_context = build_route_context(route_data)
        AgentLogger.info(f"Rebuilt route context ({len(route_context)} chars)")
    
    if not route_context:
        AgentLogger.node_exit("route_question_node", "no_route")
        return {
            "messages": [AIMessage(content="I don't have an active route to answer questions about. Would you like me to find a route first?")],
            "current_intent": "conversation"
        }
    
    # Build conversation context
    context_messages = messages[-6:-1] if len(messages) > 1 else []
    history_text = format_conversation_history(context_messages)
    
    route_qa_prompt = f"""You are a navigation assistant with detailed knowledge of the user's current route.

Below is the COMPLETE route data. Use ONLY this data to answer the user's question.
Do NOT make up information not present in the data. If the data doesn't contain what they're asking about, say so.

--- ROUTE DATA ---
{route_context}
--- END ROUTE DATA ---

Conversation history:
{history_text}

User's question: "{user_message}"

Provide a clear, specific, data-backed answer. Use numbers and road names from the data above.
Format your response nicely with bullet points or numbered lists when listing multiple items.
Be conversational but precise."""
    
    AgentLogger.llm_prompt("Route Q&A (Claude)", route_qa_prompt, num_context_messages=len(context_messages))
    
    try:
        response_text = call_claude_api([HumanMessage(content=route_qa_prompt)], purpose="route_question")
        AgentLogger.llm_response("Route Q&A", response_text)
        AgentLogger.agent_response(response_text)
        AgentLogger.node_exit("route_question_node", "route_question")
        return {
            "messages": [AIMessage(content=response_text)],
            "current_intent": "route_question"
        }
    except Exception as e:
        AgentLogger.error(f"Route Q&A error: {str(e)}")
        return {
            "messages": [AIMessage(content="I had trouble analyzing the route data. Could you try rephrasing your question?")],
            "current_intent": "error"
        }


def disambiguation_node(state: SupervisorState):
    """
    LLM-powered disambiguation — uses Claude to understand user responses naturally.
    
    Claude can handle:
    - Direct selections: "2", "the first one", "KK Nagar in Chennai"
    - Follow-up questions: "is there any in ahmedabad?", "which is closest?"
    - Re-search requests: "search for KK Nagar in Gujarat instead"
    - Abandoning: "never mind", "let's go somewhere else"
    """
    AgentLogger.node_enter("disambiguation_node")
    
    messages = state["messages"]
    user_message = messages[-1].content
    user_location = state.get("location")
    pending_candidates = state.get("pending_candidates", {})
    candidates = pending_candidates.get("candidates", [])
    context = pending_candidates.get("context", {})
    
    AgentLogger.info(f"User response: \"{user_message}\"")
    AgentLogger.info(f"Candidates: {len(candidates)}")
    
    # Format candidates for Claude
    candidates_text = format_candidates_for_llm(candidates)
    
    # Build conversation context
    recent_messages = messages[-6:-1] if len(messages) > 1 else []
    history_text = format_conversation_history(recent_messages)
    
    # Build user location context
    user_location_context = ""
    if user_location and user_location.get("lat") and user_location.get("lng"):
        user_location_context = f"\n\nIMPORTANT — The user is currently located at GPS coordinates ({user_location['lat']}, {user_location['lng']}). When they select a location or ask about options, STRONGLY prefer locations that are geographically close to them (same country/region). Do NOT select locations in a different country unless the user explicitly asks for it."
    
    disambiguation_prompt = f"""You are a navigation assistant helping a user choose a location.{user_location_context}

The user was searching for a place and I found multiple locations. Here are the candidates:

{candidates_text}

Recent conversation:
{history_text}

The user just said: "{user_message}"

Analyze the user's response and determine their intent. Respond with ONLY valid JSON:

{{
    "action": "select" | "question" | "re_search" | "abandon",
    "selected_id": <MUST be an exact ID number from the candidates list above (1-{len(candidates)}). Only set when action is "select". null otherwise>,
    "answer": "<natural language response to show the user>",
    "new_search_query": "<new search query if action is re_search, null otherwise>"
}}

CRITICAL: When action is "select", the "selected_id" MUST exactly match one of the candidate IDs listed above. Double-check that the ID corresponds to the correct location name and address before responding.

Rules:
- "select": User is picking a specific location (by number, name, description, city, or other identifier). The selected_id MUST match the candidate's ID number.
- "question": User is asking about the candidates (e.g. "which is closest?", "is there one in X city?"). Answer helpfully based on the candidate data. If they ask about a city/area not in the list, tell them and suggest re-searching.
- "re_search": User wants to search differently (e.g. "search in Ahmedabad instead", "find one near me")
- "abandon": User wants to do something else entirely (e.g. "never mind", "take me to Delhi instead")

For "select": Confirm the selection with the EXACT name and address from the candidates list.
For "question": Answer their question, then ask which location they'd like."""

    AgentLogger.llm_prompt("Disambiguation (Claude)", disambiguation_prompt, num_context_messages=len(recent_messages))
    
    try:
        claude_response = call_claude_api([HumanMessage(content=disambiguation_prompt)], purpose="disambiguation")
        AgentLogger.llm_response("Disambiguation", claude_response)
        
        # Parse Claude's JSON response
        response_text = claude_response.strip()
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        
        if json_start >= 0 and json_end > json_start:
            decision = json.loads(response_text[json_start:json_end])
        else:
            raise json.JSONDecodeError("No JSON found", response_text, 0)
        
        action = decision.get("action", "question")
        answer = decision.get("answer", "")
        
        AgentLogger.info(f"Claude decision: action={action}")
        
        # ── ACTION: SELECT ──
        if action == "select":
            selected_id = decision.get("selected_id")
            if selected_id and 1 <= selected_id <= len(candidates):
                # Safe lookup: find by ID field, not array index
                selected = None
                for c in candidates:
                    if c.get("id") == selected_id:
                        selected = c
                        break
                if selected is None:
                    # Fallback to array index
                    selected = candidates[selected_id - 1]
                
                AgentLogger.disambiguation_selected(selected)
                
                # Build route with selected location
                location_a = context.get("location_a", "")
                location_b = context.get("location_b", "")
                
                selected_coords = f"{selected['coordinates']['lat']},{selected['coordinates']['lng']}"
                if context.get("ambiguous_field") == "location_a":
                    location_a = selected_coords
                else:
                    location_b = selected_coords
                
                # Resolve the other location if needed
                if not is_coordinates(location_a) and user_location:
                    location_a = f"{user_location['lat']},{user_location['lng']}"
                
                AgentLogger.tool_call("routing_engine", {"from": location_a, "to": location_b})
                
                try:
                    route_data = routing_engine(location_a, location_b)
                    
                    # Extract alternatives before storing
                    alternatives = route_data.pop("alternative_routes", [])
                    
                    AgentLogger.state_update("route_data", route_data)
                    AgentLogger.state_update("pending_candidates", "cleared")
                    
                    # Build route context for conversational Q&A
                    route_context = build_route_context(route_data)
                    AgentLogger.info(f"Built route context ({len(route_context)} chars)")
                    
                    response = f"{answer}\n\nThe route is {route_data['distance_km']} km and will take about {route_data['time_minutes']} minutes."
                    
                    if alternatives:
                        response += f"\n\n🗺️ I also found **{len(alternatives)} alternative route(s)** — shown in grey on the map. Click any grey route to switch to it!"
                        for i, alt in enumerate(alternatives):
                            sign = "+" if alt.get("time_diff_minutes", 0) >= 0 else ""
                            response += f"\n  • Route {i+2}: {alt['distance_km']} km ({sign}{alt.get('time_diff_minutes', 0)} min)"
                    
                    response += "\n\n💡 You can now ask me anything about this route — highway details, lane counts, turn-by-turn directions, road surfaces, and more!"
                    
                    AgentLogger.agent_response(response)
                    AgentLogger.node_exit("disambiguation_node", "routing")
                    
                    return {
                        "messages": [AIMessage(content=response)],
                        "route_data": route_data,
                        "route_context": route_context,
                        "alternative_routes": alternatives,
                        "current_intent": "routing",
                        "pending_candidates": None,
                        "location_candidates": None
                    }
                except Exception as e:
                    AgentLogger.error(f"Routing after selection failed: {str(e)}")
                    return {
                        "messages": [AIMessage(content=f"{answer}\n\nHowever, I couldn't calculate the route. Please try again.")],
                        "current_intent": "error",
                        "pending_candidates": None,
                        "location_candidates": None
                    }
            else:
                # Claude said select but invalid ID — treat as question
                AgentLogger.error(f"Invalid selected_id: {selected_id}")
                action = "question"
        
        # ── ACTION: QUESTION ──
        if action == "question":
            AgentLogger.agent_response(answer)
            AgentLogger.node_exit("disambiguation_node", "disambiguation")
            # Keep pending_candidates — user hasn't chosen yet
            return {
                "messages": [AIMessage(content=answer)],
                "current_intent": "disambiguation"
            }
        
        # ── ACTION: RE-SEARCH ──
        if action == "re_search":
            new_query = decision.get("new_search_query", "")
            if new_query:
                AgentLogger.info(f"Re-searching with: \"{new_query}\"")
                AgentLogger.tool_call("search_locations", {"query": new_query, "limit": 5})
                
                search_result = search_locations.invoke({
                    "query": new_query,
                    "user_location": user_location,
                    "limit": 5
                })
                AgentLogger.tool_result("search_locations", search_result)
                
                if search_result.get("found") and search_result["locations"]:
                    new_candidates = search_result["locations"]
                    
                    if len(new_candidates) == 1 or not search_result.get("needs_disambiguation"):
                        # Single clear result — route directly
                        chosen = new_candidates[0]
                        location_a = context.get("location_a", "")
                        location_b = context.get("location_b", "")
                        
                        selected_coords = f"{chosen['coordinates']['lat']},{chosen['coordinates']['lng']}"
                        if context.get("ambiguous_field") == "location_a":
                            location_a = selected_coords
                        else:
                            location_b = selected_coords
                        
                        if not is_coordinates(location_a) and user_location:
                            location_a = f"{user_location['lat']},{user_location['lng']}"
                        
                        try:
                            route_data = routing_engine(location_a, location_b)
                            
                            # Extract alternatives before storing
                            alternatives = route_data.pop("alternative_routes", [])
                            
                            response = f"Found it! {chosen['name']} ({chosen['address']}). The route is {route_data['distance_km']} km and will take about {route_data['time_minutes']} minutes."
                            
                            if alternatives:
                                response += f"\n\n🗺️ I also found **{len(alternatives)} alternative route(s)** — shown in grey on the map. Click any grey route to switch to it!"
                                for i, alt in enumerate(alternatives):
                                    sign = "+" if alt.get("time_diff_minutes", 0) >= 0 else ""
                                    response += f"\n  • Route {i+2}: {alt['distance_km']} km ({sign}{alt.get('time_diff_minutes', 0)} min)"
                            
                            AgentLogger.agent_response(response)
                            return {
                                "messages": [AIMessage(content=response)],
                                "route_data": route_data,
                                "alternative_routes": alternatives,
                                "current_intent": "routing",
                                "pending_candidates": None,
                                "location_candidates": None
                            }
                        except Exception as e:
                            AgentLogger.error(f"Route after re-search failed: {str(e)}")
                    
                    # Multiple results — update candidates
                    response_msg = format_location_options(new_query, new_candidates)
                    AgentLogger.disambiguation_candidates(new_query, len(new_candidates), new_candidates)
                    
                    return {
                        "messages": [AIMessage(content=f"{answer}\n\n{response_msg}")],
                        "current_intent": "disambiguation",
                        "pending_candidates": {
                            "candidates": new_candidates,
                            "context": context  # Keep original routing context
                        },
                        "location_candidates": new_candidates
                    }
                else:
                    return {
                        "messages": [AIMessage(content=f"I couldn't find any results for '{new_query}'. Would you like to choose from the original options?")],
                        "current_intent": "disambiguation"
                    }
            else:
                return {
                    "messages": [AIMessage(content=answer)],
                    "current_intent": "disambiguation"
                }
        
        # ── ACTION: ABANDON ──
        if action == "abandon":
            AgentLogger.info("User abandoned disambiguation")
            AgentLogger.node_exit("disambiguation_node", "abandoned")
            return {
                "messages": [AIMessage(content=answer)],
                "current_intent": "conversation",
                "pending_candidates": None,
                "location_candidates": None
            }
        
        # Fallback
        return {
            "messages": [AIMessage(content=answer or "Could you clarify which location you'd like?")],
            "current_intent": "disambiguation"
        }
    
    except Exception as e:
        AgentLogger.error(f"Disambiguation error: {str(e)}")
        return {
            "messages": [AIMessage(content="I had trouble understanding that. Could you pick a number from the list, or tell me what you'd like to do?")],
            "current_intent": "disambiguation"
        }


# ──────────────────────────────────────────────
# Graph Construction
# ──────────────────────────────────────────────

def _route_by_intent(state: SupervisorState) -> str:
    intent = state.get("current_intent", "conversation")
    if intent == "routing":
        return "routing_node"
    elif intent == "search":
        return "search_node"
    elif intent == "disambiguation":
        return "disambiguation_node"
    elif intent == "route_question":
        return "route_question_node"
    elif intent in ("error", "clarification"):
        return END
    else:
        return "conversation_node"


def create_supervisor_agent(checkpointer=None):
    """Create the stateful supervisor agent graph."""
    workflow = StateGraph(SupervisorState)
    
    workflow.add_node("router", router_node)
    workflow.add_node("routing_node", routing_node)
    workflow.add_node("search_node", search_node)
    workflow.add_node("conversation_node", conversation_node)
    workflow.add_node("disambiguation_node", disambiguation_node)
    workflow.add_node("route_question_node", route_question_node)
    
    workflow.set_entry_point("router")
    
    workflow.add_conditional_edges("router", _route_by_intent, {
        "routing_node": "routing_node",
        "search_node": "search_node",
        "conversation_node": "conversation_node",
        "disambiguation_node": "disambiguation_node",
        "route_question_node": "route_question_node",
        END: END
    })
    
    workflow.add_edge("routing_node", END)
    workflow.add_edge("search_node", END)
    workflow.add_edge("conversation_node", END)
    workflow.add_edge("disambiguation_node", END)
    workflow.add_edge("route_question_node", END)
    
    return workflow.compile(checkpointer=checkpointer)


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def run_supervisor(user_message, session_id, checkpointer=None, location=None, user_id=None):
    """Run the supervisor agent. State persisted via checkpointer + thread_id."""
    
    AgentLogger._print_box("🚀 NEW REQUEST", AgentLogger.Colors.HEADER)
    AgentLogger.info(f"Session: {session_id[:12]}...")
    AgentLogger.info(f"Message: \"{user_message}\"")
    if location:
        AgentLogger.info(f"GPS: ({location.get('lat')}, {location.get('lng')})")
    
    agent = create_supervisor_agent(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": session_id}}
    
    input_state = {
        "messages": [HumanMessage(content=user_message)],
        "location": location or {},
    }
    
    result = agent.invoke(input_state, config=config)
    
    AgentLogger._print_section("📋 REQUEST COMPLETE", AgentLogger.Colors.GREEN)
    AgentLogger.info(f"Intent: {result.get('current_intent')}")
    AgentLogger.info(f"Response: {len(result['messages'][-1].content)} chars")
    if result.get("route_data"):
        rd = result["route_data"]
        AgentLogger.info(f"Route: {rd.get('distance_km')} km, {rd.get('time_minutes')} min")
    if result.get("location_candidates"):
        AgentLogger.info(f"Candidates: {len(result['location_candidates'])}")
    if result.get("alternative_routes"):
        AgentLogger.info(f"Alternative routes: {len(result['alternative_routes'])}")
    AgentLogger.separator()
    
    return {
        "message": result["messages"][-1].content,
        "route_data": result.get("route_data"),
        "intent": result.get("current_intent"),
        "location_candidates": result.get("location_candidates"),
        "search_results": result.get("search_results"),
        "alternative_routes": result.get("alternative_routes")
    }
