import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    # ClickUp Configuration
    CLICKUP_API_TOKEN = os.getenv('CLICKUP_API_TOKEN')
    CLICKUP_WORKSPACE_ID = os.getenv('CLICKUP_WORKSPACE_ID')
    CLICKUP_CUSTOM_FIELD_ID = os.getenv('CLICKUP_CUSTOM_FIELD_ID')
    
    # OpenRouter Configuration
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
    OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
    OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'google/gemini-2.5-pro')  # ← ΠΡΟΣΘΕΣΕ ΑΥΤΟ
    GEMINI_MODEL = "google/gemini-2.5-pro"
    GEMINI_THINKING_MODE = os.getenv('GEMINI_THINKING_MODE', 'medium')
    
    # WaveSpeed.ai Configuration
    WAVESPEED_API_KEY = os.getenv('WAVESPEED_API_KEY')
    WAVESPEED_API_URL = "https://api.wavespeed.ai/api/v3/bytedance/seedream-v4"
    
    # Flask Configuration
    FLASK_PORT = int(os.getenv('FLASK_PORT', 5000))
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    
    # Deep Research Prompt Path
    DEEP_RESEARCH_PATH = "deep_research.txt"
    
    # ClickUp API Base URL
    CLICKUP_API_BASE = "https://api.clickup.com/api/v2"

config = Config()