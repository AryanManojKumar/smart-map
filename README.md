# Nav AI Assistant

AI-powered navigation assistant with routing and POI search capabilities.

## Setup

1. Install dependencies:
```bash
pip install -r backend/requirements.txt
```

2. Configure API keys:
```bash
cp .env.example .env
# Edit .env and add your API keys
```

3. Start the backend:
```bash
python backend/api.py
```

4. Open the frontend:
```bash
# Open frontend/index.html in your browser
# Or use a simple HTTP server:
python -m http.server 3000 --directory frontend
# Then visit http://localhost:3000
```

## Usage

- Ask for directions: "Route from Times Square to Central Park"
- Search for places: "Find gas stations along route"
- Search nearby: "Where's the nearest restaurant?"

## Architecture

- **Routing Engine**: Pure API wrapper for GraphHopper
- **Search Agent**: LangGraph agent with OSM search tools
- **Frontend**: Chat interface + Leaflet map
