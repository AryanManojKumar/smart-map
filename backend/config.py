import os
from dotenv import load_dotenv

load_dotenv()

GRAPHHOPPER_API_KEY = os.getenv("GRAPHHOPPER_API_KEY")
KIE_API_KEY = os.getenv("KIE_API_KEY")
GRAPHHOPPER_BASE_URL = "https://graphhopper.com/api/1"
KIE_BASE_URL = "https://api.kie.ai"
