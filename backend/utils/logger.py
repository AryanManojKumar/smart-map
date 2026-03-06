from datetime import datetime
from typing import Any

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class AgentLogger:
    """Beautiful terminal logger for agent execution."""
    
    Colors = Colors  # Make Colors accessible as class attribute
    
    @staticmethod
    def _timestamp():
        return datetime.now().strftime("%H:%M:%S")
    
    @staticmethod
    def _print_box(text: str, color: str = Colors.BLUE):
        """Print text in a box."""
        width = len(text) + 4
        print(f"\n{color}{'═' * width}")
        print(f"║ {text} ║")
        print(f"{'═' * width}{Colors.ENDC}\n")
    
    @staticmethod
    def routing_start(location_a: str, location_b: str):
        """Log routing engine start."""
        AgentLogger._print_box("🚗 ROUTING ENGINE", Colors.CYAN)
        print(f"{Colors.CYAN}[{AgentLogger._timestamp()}] Starting route calculation...{Colors.ENDC}")
        print(f"  📍 From: {Colors.BOLD}{location_a}{Colors.ENDC}")
        print(f"  📍 To:   {Colors.BOLD}{location_b}{Colors.ENDC}")
    
    @staticmethod
    def routing_geocoding(location: str, coords: dict):
        """Log geocoding step."""
        print(f"{Colors.YELLOW}[{AgentLogger._timestamp()}] 🌍 Geocoding: {location}{Colors.ENDC}")
        print(f"  → Coordinates: {coords['lat']:.4f}, {coords['lng']:.4f}")
    
    @staticmethod
    def routing_calculating():
        """Log route calculation."""
        print(f"{Colors.YELLOW}[{AgentLogger._timestamp()}] 🧮 Calculating optimal route...{Colors.ENDC}")
    
    @staticmethod
    def routing_complete(route_data: dict):
        """Log routing completion."""
        print(f"{Colors.GREEN}[{AgentLogger._timestamp()}] ✓ Route calculated successfully!{Colors.ENDC}")
        print(f"  📏 Distance: {Colors.BOLD}{route_data['distance_km']} km{Colors.ENDC}")
        print(f"  ⏱️  Duration: {Colors.BOLD}{route_data['time_minutes']} minutes{Colors.ENDC}")
        print(f"  🗺️  Waypoints: {Colors.BOLD}{len(route_data['polyline'])} points{Colors.ENDC}")
    
    @staticmethod
    def search_start(query: str):
        """Log search agent start."""
        AgentLogger._print_box("🔍 SEARCH AGENT", Colors.BLUE)
        print(f"{Colors.BLUE}[{AgentLogger._timestamp()}] Query: {Colors.BOLD}{query}{Colors.ENDC}")
    
    @staticmethod
    def agent_thinking():
        """Log agent reasoning."""
        print(f"{Colors.YELLOW}[{AgentLogger._timestamp()}] 🤔 Agent analyzing query...{Colors.ENDC}")
    
    @staticmethod
    def tool_call(tool_name: str, args: dict):
        """Log tool invocation."""
        print(f"{Colors.CYAN}[{AgentLogger._timestamp()}] 🔧 Calling tool: {Colors.BOLD}{tool_name}{Colors.ENDC}")
        for key, value in args.items():
            if key == "polyline":
                print(f"  • {key}: [{len(value)} coordinates]")
            else:
                print(f"  • {key}: {value}")
    
    @staticmethod
    def tool_result(tool_name: str, result: Any):
        """Log tool result."""
        if isinstance(result, list):
            count = len(result)
            print(f"{Colors.GREEN}[{AgentLogger._timestamp()}] ✓ {tool_name} returned {count} results{Colors.ENDC}")
            if count > 0 and isinstance(result[0], dict):
                for i, item in enumerate(result[:3], 1):
                    name = item.get('name', 'Unknown')
                    print(f"  {i}. {name}")
                if count > 3:
                    print(f"  ... and {count - 3} more")
        else:
            print(f"{Colors.GREEN}[{AgentLogger._timestamp()}] ✓ {tool_name} completed{Colors.ENDC}")
    
    @staticmethod
    def agent_response(response: str):
        """Log agent final response."""
        print(f"{Colors.GREEN}[{AgentLogger._timestamp()}] 💬 Agent response:{Colors.ENDC}")
        print(f"{Colors.BOLD}{response}{Colors.ENDC}")
    
    @staticmethod
    def error(message: str):
        """Log error."""
        print(f"{Colors.RED}[{AgentLogger._timestamp()}] ❌ Error: {message}{Colors.ENDC}")
    
    @staticmethod
    def separator():
        """Print separator line."""
        print(f"{Colors.BLUE}{'─' * 80}{Colors.ENDC}")
