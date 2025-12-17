"""Configuration management for the Image Edit Agent."""

import os
from pathlib import Path
from typing import Dict, Any, Optional
import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .errors import ConfigurationError
from .logger import get_logger

logger = get_logger(__name__)

# Load environment variables
load_dotenv()


class ModelConfig(BaseModel):
    """Configuration for a single image model."""
    name: str
    provider: str
    priority: int
    supports_greek: bool = True


class EnhancementConfig(BaseModel):
    """Configuration for prompt enhancement."""
    model: str
    provider: str
    max_tokens: int = 2000
    temperature: float = 0.7
    cache_enabled: bool = True


class ValidationConfig(BaseModel):
    """Configuration for image validation."""
    model: str
    provider: str
    max_tokens: int = 1000
    temperature: float = 0.0
    vision_enabled: bool = True


class ProcessingConfig(BaseModel):
    """Configuration for processing behavior."""
    max_iterations: int = 3
    timeout_seconds: int = 60
    parallel_execution: bool = True


class QualityThresholds(BaseModel):
    """Quality thresholds for validation."""
    minimum_validation_score: int = 75
    greek_typography_accuracy: int = 95
    hybrid_fallback_threshold: int = 3


class Config(BaseModel):
    """Main application configuration."""
    
    # API Keys
    openrouter_api_key: str = Field(..., alias="OPENROUTER_API_KEY")
    wavespeed_api_key: str = Field(..., alias="WAVESPEED_API_KEY")
    clickup_api_key: str = Field(..., alias="CLICKUP_API_KEY")
    clickup_webhook_secret: str = Field(..., alias="CLICKUP_WEBHOOK_SECRET")
    
    # Application Settings
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    max_iterations: int = Field(default=3, alias="MAX_ITERATIONS")

    max_step_attempts: int = Field(default=2, alias="MAX_STEP_ATTEMPTS")
    validation_pass_threshold: int = Field(default=8, alias="VALIDATION_PASS_THRESHOLD")
    
    # Rate Limiting
    rate_limit_enhancement: int = Field(default=5, alias="RATE_LIMIT_ENHANCEMENT")
    rate_limit_validation: int = Field(default=3, alias="RATE_LIMIT_VALIDATION")
    
    # Timeout Settings
    timeout_openrouter_seconds: float = Field(default=120.0, alias="TIMEOUT_OPENROUTER_SECONDS")
    
    # Model Configuration
    image_models: list[ModelConfig] = []
    enhancement: Optional[EnhancementConfig] = None
    validation: Optional[ValidationConfig] = None
    processing: Optional[ProcessingConfig] = None
    quality_thresholds: Optional[QualityThresholds] = None
    
    # Paths
    config_dir: Path = Path("config")
    deep_research_dir: Path = Path("config/deep_research")
    prompts_dir: Path = Path("config/prompts")
    
    class Config:
        populate_by_name = True


# Global config instance
_config: Optional[Config] = None


def load_config() -> Config:
    """
    Load configuration from environment and YAML files.
    
    Returns:
        Config instance
        
    Raises:
        ConfigurationError: If configuration is invalid
    """
    global _config
    
    try:
        # Load models.yaml
        models_path = Path("config/models.yaml")
        if not models_path.exists():
            raise ConfigurationError(f"models.yaml not found at {models_path}")
        
        with open(models_path, "r") as f:
            models_config = yaml.safe_load(f)
        
        # Merge environment variables with YAML config
        config_data = {
            **os.environ,  # Environment variables
            **models_config,  # YAML config
        }
        
        _config = Config(**config_data)
        
        logger.info(
            "Configuration loaded successfully",
            extra={
                "models_count": len(_config.image_models),
                "environment": _config.app_env,
            }
        )
        
        return _config
        
    except Exception as e:
        raise ConfigurationError(f"Failed to load configuration: {e}")


def get_config() -> Config:
    """
    Get the current configuration instance.
    
    Returns:
        Config instance
        
    Raises:
        ConfigurationError: If config not loaded
    """
    if _config is None:
        raise ConfigurationError("Configuration not loaded. Call load_config() first.")
    return _config


def load_deep_research(model_name: str) -> Dict[str, str]:
    """
    Load deep research files for a specific model.
    
    Args:
        model_name: Name of the model (e.g., 'seedream-v4')
        
    Returns:
        Dict with 'activation' and 'research' content
        
    Raises:
        ConfigurationError: If research files not found
    """
    config = get_config()
    model_dir = config.deep_research_dir / model_name
    
    activation_path = model_dir / "activation.txt"
    research_path = model_dir / "research.md"
    
    if not activation_path.exists():
        raise ConfigurationError(f"Activation file not found: {activation_path}")
    
    if not research_path.exists():
        raise ConfigurationError(f"Research file not found: {research_path}")
    
    with open(activation_path, "r", encoding="utf-8") as f:
        activation = f.read()
    
    with open(research_path, "r", encoding="utf-8") as f:
        research = f.read()
    
    return {
        "activation": activation,
        "research": research,
    }


def load_validation_prompt() -> str:
    """
    Load the validation prompt template.
    
    Returns:
        Validation prompt string
        
    Raises:
        ConfigurationError: If prompt file not found
    """
    config = get_config()
    prompt_path = config.prompts_dir / "validation_prompt.txt"
    
    if not prompt_path.exists():
        raise ConfigurationError(f"Validation prompt not found: {prompt_path}")
    
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


# ═══════════════════════════════════════════════════════════════
# FONTS GUIDE LOADER (cached)
# ═══════════════════════════════════════════════════════════════

_fonts_guide_cache: Optional[str] = None


def load_fonts_guide() -> str:
    """
    Load fonts translation guide (cached).
    
    Returns:
        Fonts guide content or empty string if not found
    """
    global _fonts_guide_cache
    
    if _fonts_guide_cache is not None:
        return _fonts_guide_cache
    
    try:
        fonts_path = Path(__file__).parent.parent.parent / "config" / "shared" / "fonts.md"
        if fonts_path.exists():
            _fonts_guide_cache = fonts_path.read_text(encoding='utf-8')
            logger.info(f"Loaded fonts guide: {len(_fonts_guide_cache)} chars")
        else:
            _fonts_guide_cache = ""
            logger.warning(f"fonts.md not found at {fonts_path}")
    except Exception as e:
        logger.warning(f"Failed to load fonts guide: {e}")
        _fonts_guide_cache = ""
    
    return _fonts_guide_cache