from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from backend.models.state import SupervisorState
from backend.agents.routing_engine import routing_engine
from backend.agents.search_agent import run_search_agent
from backend.config import KIE_API_KEY, KIE_BASE_URL
from backend.utils.logger import AgentLogger
import json
import requests

def create_supervisor_agent():
    """Create and return the supervisor agent graph."""
    
    def call_kie_api(messages):
        """Direct API call to Kie to handle response format."""
        headers = {
            "Authorization": f"Bearer {KIE_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Convert messages to proper format
        formatted_messages = []
        for msg in messages:
            role = "system" if isinstance(msg, SystemMessage) else "user"
            formatted_messages.append({"role": role, "content": msg.content})
        
        payload = {
            "model": "gemini-3-pro",
            "messages": formatted_messages,
            "temperature": 0
        }
        
        print(f"{AgentLogger.Colors.YELLOW}[Debug] Calling Kie API...{AgentLogger.Colors.ENDC}")
        
        response = requests.post(
            f"{KIE_BASE_URL}/gemini-3-pro/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        print(f"{AgentLogger.Colors.YELLOW}[Debug] Status: {response.status_code}{AgentLogger.Colors.ENDC}")
        
        data = response.json()
        print(f"{AgentLogger.Colors.YELLOW}[Debug] Response keys: {list(data.keys())}{AgentLogger.Colors.ENDC}")
        
        # Handle different response formats
        if "choices" in data and data["choices"] and len(data["choices"]) > 0:
            content = data["choices"][0].get("message", {}).get("content")
            if content:
                return content
        
        if "data" in data and data["data"]:
            return str(data["data"])
        
        if "msg" in data:
            print(f"{AgentLogger.Colors.RED}[Debug] API Error: {data['msg']}{AgentLogger.Colors.ENDC}")
        
        # Print full response for debugging
        print(f"{AgentLogger.Colors.RED}[Debug] Full response: {json.dumps(data, indent=2)}{AgentLogger.Colors.ENDC}")
        
        raise Exception(f"Could not extract content from API response. Keys: {list(data.keys())}")
    
    def supervisor_node(state: SupervisorState):
        """Main supervisor reasoning node with LLM-based intent detection."""
        AgentLogger._print_box("🎯 SUPERVISOR AGENT", AgentLogger.Colors.HEADER)
        
        messages = state["messages"]
        user_message = messages[-1].content
        
        # Use LLM to understand intent and extract information
        intent_prompt = """You are a navigation assistant supervisor. Analyze the user's message and determine their intent.

Your job is to extract:
1. Intent: "routing", "search", or "conversation"
2. If routing: Extract location_a and location_b (the start and destination)
3. If search: Extract what they're searching for (poi_type like "gas station", "restaurant", etc.)

User message: "{message}"

Respond ONLY with valid JSON in this exact format:
{{
    "intent": "routing" or "search" or "conversation",
    "location_a": "extracted start location" (only for routing),
    "location_b": "extracted destination" (only for routing),
    "poi_type": "what to search for" (only for search),
    "clarification_needed": true/false,
    "clarification_message": "what to ask user" (if clarification needed)
}}

Examples:
- "show me directions from Meerut to Noida" → {{"intent": "routing", "location_a": "Meerut", "location_b": "Noida", "clarification_needed": false}}
- "I want to go to Delhi from here" → {{"intent": "routing", "clarification_needed": true, "clarification_message": "Where are you starting from?"}}
- "find gas stations" → {{"intent": "search", "poi_type": "gas station", "clarification_needed": false}}
- "hello" → {{"intent": "conversation", "clarification_needed": false}}"""
        
        print(f"{AgentLogger.Colors.YELLOW}[Supervisor] 🤔 Analyzing user intent...{AgentLogger.Colors.ENDC}")
        
        try:
            # Combine system prompt with user message for intent detection
            combined_prompt = intent_prompt.format(message=user_message)
            
            intent_response = call_kie_api([
                HumanMessage(content=combined_prompt)
            ])
            
            print(f"{AgentLogger.Colors.YELLOW}[Debug] LLM Response: {intent_response[:200]}...{AgentLogger.Colors.ENDC}")
            
            # Try to extract JSON from response (LLM might add extra text)
            response_text = intent_response.strip()
            
            # Find JSON in response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                intent_data = json.loads(json_str)
            else:
                raise json.JSONDecodeError("No JSON found", response_text, 0)
            
            print(f"{AgentLogger.Colors.CYAN}[Supervisor] Intent: {intent_data['intent']}{AgentLogger.Colors.ENDC}")
            
            # Handle clarification needed
            if intent_data.get("clarification_needed"):
                return {
                    "messages": [AIMessage(content=intent_data["clarification_message"])],
                    "current_intent": "clarification"
                }
            
            # Handle routing
            if intent_data["intent"] == "routing":
                location_a = intent_data.get("location_a")
                location_b = intent_data.get("location_b")
                
                if not location_a or not location_b:
                    return {
                        "messages": [AIMessage(content="I need both a starting location and destination. Could you provide both?")],
                        "current_intent": "clarification"
                    }
                
                print(f"{AgentLogger.Colors.CYAN}[Supervisor] Routing: {location_a} → {location_b}{AgentLogger.Colors.ENDC}")
                print(f"  → Delegating to Routing Engine")
                
                try:
                    route_data = routing_engine(location_a, location_b)
                    
                    response = f"I found a route from {route_data['from']} to {route_data['to']}! It's {route_data['distance_km']} km and will take about {route_data['time_minutes']} minutes."
                    
                    return {
                        "messages": [AIMessage(content=response)],
                        "route_data": route_data,
                        "current_intent": "routing"
                    }
                except Exception as e:
                    AgentLogger.error(f"Routing failed: {str(e)}")
                    return {
                        "messages": [AIMessage(content=f"Sorry, I couldn't find a route between those locations. Please check the location names and try again.")],
                        "current_intent": "error"
                    }
            
            # Handle search
            elif intent_data["intent"] == "search":
                poi_type = intent_data.get("poi_type")
                
                print(f"{AgentLogger.Colors.CYAN}[Supervisor] Search: {poi_type}{AgentLogger.Colors.ENDC}")
                print(f"  → Delegating to Search Agent")
                
                try:
                    result = run_search_agent(
                        user_message,
                        route_data=state.get("route_data"),
                        location=state.get("location")
                    )
                    
                    agent_response = result["messages"][-1].content
                    
                    return {
                        "messages": [AIMessage(content=agent_response)],
                        "current_intent": "search"
                    }
                except Exception as e:
                    AgentLogger.error(f"Search failed: {str(e)}")
                    return {
                        "messages": [AIMessage(content=f"Sorry, I couldn't complete the search. Please try again.")],
                        "current_intent": "error"
                    }
            
            # Handle general conversation
            else:
                print(f"{AgentLogger.Colors.CYAN}[Supervisor] General conversation{AgentLogger.Colors.ENDC}")
                
                conversation_prompt = """You are a friendly and helpful navigation assistant named Nav AI. 

Your capabilities:
- Find routes between any two locations worldwide
- Search for places like gas stations, restaurants, hotels, parking, etc.
- Provide navigation assistance and travel information

Your personality:
- Helpful and enthusiastic about helping people navigate
- Clear and concise in your responses
- Proactive in asking for missing information
- Knowledgeable about navigation and travel

User message: {message}

Respond naturally to the user's message. If they're greeting you or asking what you can do, introduce yourself warmly."""
                
                response_text = call_kie_api([
                    HumanMessage(content=conversation_prompt.format(message=user_message))
                ])
                
                return {
                    "messages": [AIMessage(content=response_text)],
                    "current_intent": "conversation"
                }
        
        except json.JSONDecodeError as e:
            AgentLogger.error(f"Failed to parse intent: {str(e)}")
            # Fallback to conversation
            return {
                "messages": [AIMessage(content="I'm here to help with navigation! You can ask me for directions between locations or to find places nearby.")],
                "current_intent": "conversation"
            }
        except Exception as e:
            AgentLogger.error(f"Supervisor error: {str(e)}")
            return {
                "messages": [AIMessage(content="I'm here to help with navigation! You can ask me for directions between locations or to find places nearby.")],
                "current_intent": "error"
            }
    
    # Build graph
    workflow = StateGraph(SupervisorState)
    workflow.add_node("supervisor", supervisor_node)
    workflow.set_entry_point("supervisor")
    workflow.add_edge("supervisor", END)
    
    return workflow.compile()

def run_supervisor(user_message: str, route_data: dict = None, location: dict = None):
    """
    Run the supervisor agent with a user message.
    
    Args:
        user_message: User's input message
        route_data: Optional existing route data
        location: Optional user location
    
    Returns:
        Response with message, route_data, and pois
    """
    
    agent = create_supervisor_agent()
    
    initial_state = {
        "messages": [HumanMessage(content=user_message)],
        "route_data": route_data or {},
        "location": location or {},
        "current_intent": "unknown"
    }
    
    result = agent.invoke(initial_state)
    
    AgentLogger.separator()
    
    return {
        "message": result["messages"][-1].content,
        "route_data": result.get("route_data"),
        "intent": result.get("current_intent")
    }
