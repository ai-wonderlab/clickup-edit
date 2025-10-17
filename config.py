import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    # ClickUp Configuration
    CLICKUP_API_TOKEN = os.getenv('CLICKUP_API_TOKEN')
    CLICKUP_WORKSPACE_ID = os.getenv('CLICKUP_WORKSPACE_ID')
    CLICKUP_CUSTOM_FIELD_ID = os.getenv('CLICKUP_CUSTOM_FIELD_ID')
    CLICKUP_API_BASE = os.getenv('CLICKUP_API_BASE', 'https://api.clickup.com/api/v2')
    
    # OpenRouter Configuration (Gemini)
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
    OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'anthropic/claude-sonnet-4.5')
    OPENROUTER_VALIDATION_MODEL = os.getenv('OPENROUTER_VALIDATION_MODEL', 'anthropic/claude-3.5-sonnet')
    GEMINI_THINKING_MODE = os.getenv('GEMINI_THINKING_MODE', 'high')
    
    # WaveSpeed.ai Configuration (SeaDream)
    WAVESPEED_API_KEY = os.getenv('WAVESPEED_API_KEY')
    
    # Redis Configuration
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # Flask Configuration
    FLASK_PORT = int(os.getenv('FLASK_PORT', 5000))
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

config = Config()