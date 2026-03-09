"""
Agent Logger — Rich terminal output for debugging agent execution.

Provides CrewAI-style verbose logging showing:
- Node transitions and graph flow
- API calls (endpoint, model, payload size)
- LLM responses (full or truncated)
- Tool invocations and results
- State changes and conversation context
"""

from datetime import datetime
from typing import Any
import json


class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[35m'
    WHITE = '\033[97m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    UNDERLINE = '\033[4m'


class AgentLogger:
    """Rich terminal logger for agent execution — CrewAI-style verbose output."""
    
    Colors = Colors  # Make Colors accessible as class attribute
    VERBOSE = True    # Set to False to suppress detailed logs
    
    @staticmethod
    def _timestamp():
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]
    
    @staticmethod
    def _print_box(text: str, color: str = Colors.BLUE):
        """Print text in a box."""
        width = len(text) + 4
        print(f"\n{color}{'═' * width}")
        print(f"║ {text} ║")
        print(f"{'═' * width}{Colors.ENDC}\n")
    
    @staticmethod
    def _print_section(title: str, color: str = Colors.CYAN):
        """Print a section header."""
        print(f"\n{color}{'─' * 60}")
        print(f"  {title}")
        print(f"{'─' * 60}{Colors.ENDC}")
    
    # ── Node Transitions ─────────────────────
    
    @staticmethod
    def node_enter(node_name: str, details: str = ""):
        """Log entering a graph node."""
        emoji_map = {
            "router": "🧭",
            "routing_node": "🚗",
            "search_node": "🔍",
            "conversation_node": "💬",
            "disambiguation_node": "📍",
        }
        emoji = emoji_map.get(node_name, "⚙️")
        print(f"\n{Colors.BOLD}{Colors.HEADER}{'=' * 60}")
        print(f"  {emoji}  ENTERING NODE: {node_name.upper()}")
        if details:
            print(f"  {Colors.DIM}{details}{Colors.ENDC}{Colors.BOLD}{Colors.HEADER}")
        print(f"{'=' * 60}{Colors.ENDC}")
    
    @staticmethod
    def node_exit(node_name: str, result_intent: str = ""):
        """Log exiting a graph node."""
        print(f"{Colors.DIM}[{AgentLogger._timestamp()}] ◀ Exiting {node_name}" + 
              (f" → intent: {result_intent}" if result_intent else "") +
              f"{Colors.ENDC}")
    
    @staticmethod
    def node_route(from_node: str, to_node: str, reason: str = ""):
        """Log routing decision between nodes."""
        print(f"\n{Colors.MAGENTA}[{AgentLogger._timestamp()}] 🔀 ROUTING: {from_node} → {to_node}")
        if reason:
            print(f"  Reason: {reason}")
        print(f"{Colors.ENDC}")
    
    # ── API Calls ─────────────────────────────
    
    @staticmethod
    def api_call(service: str, endpoint: str, model: str = "", payload_size: int = 0):
        """Log an outgoing API call."""
        print(f"\n{Colors.YELLOW}[{AgentLogger._timestamp()}] 🌐 API CALL → {Colors.BOLD}{service}{Colors.ENDC}")
        print(f"{Colors.YELLOW}  URL: {endpoint}")
        if model:
            print(f"  Model: {model}")
        if payload_size:
            print(f"  Payload: ~{payload_size} chars")
        print(f"{Colors.ENDC}")
    
    @staticmethod
    def api_response(service: str, status_code: int = 200, response_preview: str = ""):
        """Log an API response."""
        color = Colors.GREEN if status_code == 200 else Colors.RED
        print(f"{color}[{AgentLogger._timestamp()}] ✓ {service} responded (HTTP {status_code}){Colors.ENDC}")
        if response_preview and AgentLogger.VERBOSE:
            # Show first 300 chars of response
            preview = response_preview[:300]
            if len(response_preview) > 300:
                preview += "..."
            print(f"{Colors.DIM}  Response: {preview}{Colors.ENDC}")
    
    # ── LLM Interactions ──────────────────────
    
    @staticmethod
    def llm_prompt(purpose: str, prompt_text: str, num_context_messages: int = 0):
        """Log the prompt being sent to the LLM."""
        print(f"\n{Colors.CYAN}[{AgentLogger._timestamp()}] 🧠 LLM PROMPT ({purpose}){Colors.ENDC}")
        if num_context_messages > 0:
            print(f"{Colors.DIM}  Context: {num_context_messages} prior messages included{Colors.ENDC}")
        if AgentLogger.VERBOSE:
            # Show the prompt, truncated
            lines = prompt_text.strip().split('\n')
            if len(lines) > 15:
                for line in lines[:8]:
                    print(f"{Colors.DIM}  │ {line}{Colors.ENDC}")
                print(f"{Colors.DIM}  │ ... ({len(lines) - 15} lines omitted) ...{Colors.ENDC}")
                for line in lines[-7:]:
                    print(f"{Colors.DIM}  │ {line}{Colors.ENDC}")
            else:
                for line in lines:
                    print(f"{Colors.DIM}  │ {line}{Colors.ENDC}")
    
    @staticmethod
    def llm_response(purpose: str, response_text: str):
        """Log the LLM response."""
        print(f"\n{Colors.GREEN}[{AgentLogger._timestamp()}] 💡 LLM RESPONSE ({purpose}){Colors.ENDC}")
        if AgentLogger.VERBOSE:
            preview = response_text[:500]
            if len(response_text) > 500:
                preview += f"\n  ... ({len(response_text) - 500} more chars)"
            for line in preview.split('\n'):
                print(f"{Colors.GREEN}  │ {line}{Colors.ENDC}")
    
    @staticmethod
    def llm_parsed_intent(intent_data: dict):
        """Log the parsed intent from LLM response."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}[{AgentLogger._timestamp()}] 🎯 PARSED INTENT:{Colors.ENDC}")
        for key, value in intent_data.items():
            if value:  # Only show non-empty fields
                print(f"{Colors.CYAN}  • {key}: {Colors.BOLD}{value}{Colors.ENDC}")
    
    # ── Conversation Context ──────────────────
    
    @staticmethod
    def conversation_context(messages, max_show: int = 5):
        """Log the conversation history being used."""
        if not messages:
            print(f"{Colors.DIM}[{AgentLogger._timestamp()}] 📜 Conversation context: (empty — first message){Colors.ENDC}")
            return
        
        print(f"\n{Colors.DIM}[{AgentLogger._timestamp()}] 📜 Conversation context ({len(messages)} messages):{Colors.ENDC}")
        show = messages[-max_show:] if len(messages) > max_show else messages
        if len(messages) > max_show:
            print(f"{Colors.DIM}  ... ({len(messages) - max_show} older messages hidden) ...{Colors.ENDC}")
        for msg in show:
            role = "👤 User" if hasattr(msg, 'type') and msg.type == "human" else "🤖 Assistant"
            content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            print(f"{Colors.DIM}  {role}: {content}{Colors.ENDC}")
    
    # ── Tool Calls ────────────────────────────
    
    @staticmethod
    def tool_call(tool_name: str, args: dict):
        """Log a tool invocation."""
        print(f"\n{Colors.CYAN}[{AgentLogger._timestamp()}] 🔧 TOOL CALL: {Colors.BOLD}{tool_name}{Colors.ENDC}")
        for key, value in args.items():
            if key == "polyline":
                print(f"{Colors.CYAN}  • {key}: [{len(value)} coordinates]{Colors.ENDC}")
            elif isinstance(value, str) and len(str(value)) > 100:
                print(f"{Colors.CYAN}  • {key}: {str(value)[:100]}...{Colors.ENDC}")
            else:
                print(f"{Colors.CYAN}  • {key}: {value}{Colors.ENDC}")
    
    @staticmethod
    def tool_result(tool_name: str, result: Any):
        """Log a tool result."""
        if isinstance(result, list):
            count = len(result)
            print(f"{Colors.GREEN}[{AgentLogger._timestamp()}] ✓ {tool_name} → {count} results{Colors.ENDC}")
            if count > 0 and isinstance(result[0], dict):
                for i, item in enumerate(result[:3], 1):
                    name = item.get('name', 'Unknown')
                    dist = item.get('distance_km', '')
                    extra = f" ({dist} km)" if dist else ""
                    print(f"{Colors.GREEN}  {i}. {name}{extra}{Colors.ENDC}")
                if count > 3:
                    print(f"{Colors.GREEN}  ... and {count - 3} more{Colors.ENDC}")
        elif isinstance(result, dict):
            print(f"{Colors.GREEN}[{AgentLogger._timestamp()}] ✓ {tool_name} → {json.dumps(result, indent=2)[:200]}{Colors.ENDC}")
        else:
            print(f"{Colors.GREEN}[{AgentLogger._timestamp()}] ✓ {tool_name} completed{Colors.ENDC}")
    
    # ── Routing Engine ────────────────────────
    
    @staticmethod
    def routing_start(location_a: str, location_b: str):
        """Log routing engine start."""
        AgentLogger._print_section("🚗 ROUTING ENGINE")
        print(f"  📍 From: {Colors.BOLD}{location_a}{Colors.ENDC}")
        print(f"  📍 To:   {Colors.BOLD}{location_b}{Colors.ENDC}")
    
    @staticmethod
    def routing_geocoding(location: str, coords: dict):
        """Log geocoding step."""
        print(f"{Colors.YELLOW}[{AgentLogger._timestamp()}] 🌍 Geocoded: {location} → ({coords['lat']:.4f}, {coords['lng']:.4f}){Colors.ENDC}")
    
    @staticmethod
    def routing_calculating():
        """Log route calculation."""
        print(f"{Colors.YELLOW}[{AgentLogger._timestamp()}] 🧮 Computing optimal route...{Colors.ENDC}")
    
    @staticmethod
    def routing_complete(route_data: dict):
        """Log routing completion."""
        print(f"{Colors.GREEN}[{AgentLogger._timestamp()}] ✅ Route computed!{Colors.ENDC}")
        print(f"  📏 Distance: {Colors.BOLD}{route_data['distance_km']} km{Colors.ENDC}")
        print(f"  ⏱️  Duration: {Colors.BOLD}{route_data['time_minutes']} minutes{Colors.ENDC}")
        print(f"  🗺️  Waypoints: {Colors.BOLD}{len(route_data['polyline'])} points{Colors.ENDC}")
    
    # ── Search Agent ──────────────────────────
    
    @staticmethod
    def search_start(query: str):
        """Log search agent start."""
        AgentLogger._print_section("🔍 SEARCH AGENT")
        print(f"  Query: {Colors.BOLD}{query}{Colors.ENDC}")
    
    @staticmethod
    def agent_thinking():
        """Log agent reasoning."""
        print(f"{Colors.YELLOW}[{AgentLogger._timestamp()}] 🤔 Agent analyzing...{Colors.ENDC}")
    
    @staticmethod
    def agent_response(response: str):
        """Log agent final response."""
        print(f"\n{Colors.GREEN}[{AgentLogger._timestamp()}] 💬 FINAL RESPONSE:{Colors.ENDC}")
        for line in response.split('\n'):
            print(f"{Colors.GREEN}{Colors.BOLD}  │ {line}{Colors.ENDC}")
    
    # ── Disambiguation ────────────────────────
    
    @staticmethod
    def disambiguation_candidates(query: str, count: int, candidates: list):
        """Log disambiguation candidates found."""
        print(f"\n{Colors.MAGENTA}[{AgentLogger._timestamp()}] 📍 DISAMBIGUATION: '{query}' → {count} locations{Colors.ENDC}")
        for c in candidates[:5]:
            dist = f" ({c.get('distance_text', '')})" if c.get('distance_text') else ""
            print(f"{Colors.MAGENTA}  {c['id']}. {c['name']} — {c['address']}{dist}{Colors.ENDC}")
    
    @staticmethod
    def disambiguation_selected(candidate: dict):
        """Log user's disambiguation selection."""
        print(f"\n{Colors.GREEN}[{AgentLogger._timestamp()}] ✅ SELECTED: {candidate['name']}")
        print(f"  📍 {candidate['address']}")
        print(f"  📐 ({candidate['coordinates']['lat']:.4f}, {candidate['coordinates']['lng']:.4f}){Colors.ENDC}")
    
    # ── State Changes ─────────────────────────
    
    @staticmethod
    def state_update(field: str, value: Any):
        """Log a state field being updated."""
        if isinstance(value, dict):
            preview = json.dumps(value)[:100]
        elif isinstance(value, list):
            preview = f"[{len(value)} items]"
        else:
            preview = str(value)[:100]
        print(f"{Colors.DIM}[{AgentLogger._timestamp()}] 📝 State: {field} = {preview}{Colors.ENDC}")
    
    # ── General ───────────────────────────────
    
    @staticmethod
    def error(message: str):
        """Log error."""
        print(f"\n{Colors.RED}[{AgentLogger._timestamp()}] ❌ ERROR: {message}{Colors.ENDC}")
    
    @staticmethod
    def separator():
        """Print separator line."""
        print(f"{Colors.BLUE}{'─' * 60}{Colors.ENDC}")
    
    @staticmethod
    def info(message: str):
        """Log info message."""
        print(f"{Colors.CYAN}[{AgentLogger._timestamp()}] ℹ️  {message}{Colors.ENDC}")
