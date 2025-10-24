"""
Configuration for ClickUp Image Processing System
"""
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
    
    # OpenRouter Configuration (Claude for prompts and validation)
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
    OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'anthropic/claude-3-opus')  # For prompt generation
    OPENROUTER_VALIDATION_MODEL = os.getenv('OPENROUTER_VALIDATION_MODEL', 'anthropic/claude-3.5-sonnet')  # For validation
    
    # WaveSpeed.ai Configuration
    WAVESPEED_API_KEY = os.getenv('WAVESPEED_API_KEY')
    
    # Redis Configuration
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # Proxy Server Configuration (IMPORTANT!)
    PROXY_BASE_URL = os.getenv('PROXY_BASE_URL', 'http://localhost:5001')  # Change to your Railway URL in production
    PROXY_PORT = os.getenv('PROXY_PORT', '5001')
    YOUR_SITE_URL = os.getenv('YOUR_SITE_URL', 'http://localhost:5000')  # Your main app URL
    
    # Flask Configuration
    FLASK_PORT = int(os.getenv('FLASK_PORT', 5000))
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # Rate Limiting
    MAX_CONCURRENT_TASKS = int(os.getenv('MAX_CONCURRENT_TASKS', '5'))
    RATE_LIMIT_WINDOW = int(os.getenv('RATE_LIMIT_WINDOW', '60'))
    
    # Celery Configuration
    CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
    CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
    
    def validate(self):
        """Validate required configuration"""
        required = [
            'CLICKUP_API_TOKEN',
            'WAVESPEED_API_KEY', 
            'OPENROUTER_API_KEY',
            'REDIS_URL',
            'PROXY_BASE_URL'
        ]
        
        missing = [key for key in required if not getattr(self, key)]
        if missing:
            raise ValueError(f"Missing required config: {', '.join(missing)}")
        
        return True

config = Config()