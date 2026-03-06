from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from backend.models.state import SearchAgentState
from backend.tools.osm_search_tool import search_poi_along_route, search_poi_nearby
from backend.config import KIE_API_KEY, KIE_BASE_URL
from backend.utils.logger import AgentLogger

def create_search_agent():
    """Create and return the search agent graph."""
    
    llm = ChatOpenAI(
        model="gemini-3-pro",
        api_key=KIE_API_KEY,
        base_url=f"{KIE_BASE_URL}/gemini-3-pro/v1"
    )
    
    tools = [search_poi_along_route, search_poi_nearby]
    llm_with_tools = llm.bind_tools(tools)
    
    def agent_node(state: SearchAgentState):
        """Main agent reasoning node."""
        AgentLogger.agent_thinking()
        messages = state["messages"]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}
    
    def should_continue(state: SearchAgentState):
        """Determine if we should continue or end."""
        messages = state["messages"]
        last_message = messages[-1]
        
        if last_message.tool_calls:
            return "tools"
        return END
    
    # Build graph
    workflow = StateGraph(SearchAgentState)
    
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(tools))
    
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")
    
    return workflow.compile()

def run_search_agent(query: str, route_data: dict = None, location: dict = None):
    """
    Run the search agent to find POIs.
    
    Args:
        query: User's search query (e.g., "Find gas stations along route")
        route_data: Optional route data with polyline
        location: Optional current location {"lat": x, "lng": y}
    
    Returns:
        Search results with POI information
    """
    
    AgentLogger.search_start(query)
    
    agent = create_search_agent()
    
    system_prompt = """You are a search assistant specializing in finding Points of Interest (POIs).
    
You have access to two tools:
1. search_poi_along_route - Use when user has a route and wants POIs along it
2. search_poi_nearby - Use when searching near a specific location

Common POI types: fuel, charging_station, restaurant, cafe, atm, parking, hotel, hospital

Analyze the user's query and use the appropriate tool."""
    
    context = ""
    if route_data:
        context += f"\nRoute available with {len(route_data.get('polyline', []))} points."
    if location:
        context += f"\nCurrent location: {location['lat']}, {location['lng']}"
    
    initial_state = {
        "messages": [
            SystemMessage(content=system_prompt + context),
            HumanMessage(content=query)
        ],
        "route_data": route_data or {},
        "location": location or {},
        "search_results": []
    }
    
    result = agent.invoke(initial_state)
    
    # Log final response
    final_message = result["messages"][-1].content
    AgentLogger.agent_response(final_message)
    AgentLogger.separator()
    
    return result
