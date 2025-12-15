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
    
    # ✅ NEW: ClickUp Configuration
    clickup_custom_field_id_ai_edit: str = Field(
        default="b2c19afd-0ef2-485c-94b9-3a6124374ff4",
        alias="CLICKUP_CUSTOM_FIELD_ID_AI_EDIT"
    )
    clickup_status_complete: str = Field(default="Complete", alias="CLICKUP_STATUS_COMPLETE")
    clickup_status_blocked: str = Field(default="blocked", alias="CLICKUP_STATUS_BLOCKED")
    clickup_status_needs_review: str = Field(default="Needs Human Review", alias="CLICKUP_STATUS_NEEDS_REVIEW")
    
    # ✅ NEW: Rate Limits
    rate_limit_enhancement: int = Field(default=3, alias="RATE_LIMIT_ENHANCEMENT")
    rate_limit_validation: int = Field(default=2, alias="RATE_LIMIT_VALIDATION")
    validation_delay_seconds: int = Field(default=2, alias="VALIDATION_DELAY_SECONDS")
    
    # ✅ NEW: Timeouts
    timeout_openrouter_seconds: int = Field(default=120, alias="TIMEOUT_OPENROUTER_SECONDS")
    timeout_wavespeed_seconds: int = Field(default=120, alias="TIMEOUT_WAVESPEED_SECONDS")
    timeout_wavespeed_polling_seconds: int = Field(default=300, alias="TIMEOUT_WAVESPEED_POLLING_SECONDS")
    timeout_clickup_seconds: int = Field(default=30, alias="TIMEOUT_CLICKUP_SECONDS")
    
    # ✅ NEW: Locking
    lock_ttl_seconds: int = Field(default=3600, alias="LOCK_TTL_SECONDS")
    lock_cleanup_interval: int = Field(default=100, alias="LOCK_CLEANUP_INTERVAL")
    
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
    
    Priority (highest to lowest):
    1. Environment variables
    2. config/config.yaml
    3. config/models.yaml
    
    Returns:
        Config instance
        
    Raises:
        ConfigurationError: If configuration is invalid
    """
    global _config
    
    try:
        # ✅ NEW: Load config.yaml (optional)
        config_yaml_path = Path("config/config.yaml")
        config_yaml_data = {}
        if config_yaml_path.exists():
            with open(config_yaml_path, "r") as f:
                config_yaml_data = yaml.safe_load(f) or {}
        
        # Load models.yaml (required)
        models_path = Path("config/models.yaml")
        models_config = {}
        if models_path.exists():
            with open(models_path, "r") as f:
                models_config = yaml.safe_load(f) or {}
        else:
            # models.yaml is still required for model definitions
            raise ConfigurationError(f"models.yaml not found at {models_path}")
        
        # ✅ NEW: Merge all sources (priority: env > config.yaml > models.yaml)
        config_data = {
            **models_config,      # Lowest priority
            **config_yaml_data,   # Middle priority
            **os.environ,         # Highest priority (env overrides)
        }
        
        # ✅ NEW: Flatten nested dicts for Pydantic
        flattened = {}
        for key, value in config_data.items():
            if isinstance(value, dict):
                # Flatten nested dicts (e.g., clickup.statuses.complete -> clickup_statuses_complete)
                for subkey, subvalue in value.items():
                    if isinstance(subvalue, dict):
                        # Handle double-nested (e.g., clickup.statuses.complete)
                        for subsubkey, subsubvalue in subvalue.items():
                            flat_key = f"{key}_{subkey}_{subsubkey}"
                            flattened[flat_key] = subsubvalue
                    else:
                        flat_key = f"{key}_{subkey}"
                        flattened[flat_key] = subvalue
            else:
                flattened[key] = value
        
        _config = Config(**flattened)
        
        logger.info(
            "Configuration loaded successfully",
            extra={
                "models_count": len(_config.image_models),
                "environment": _config.app_env,
                "config_yaml_loaded": config_yaml_path.exists(),
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
    
    # Special handling for nano-banana-pro/edit-ultra -> nano-banana-pro-edit-ultra folder
    folder_name = model_name.replace("/", "-") if "/" in model_name else model_name
    model_dir = config.deep_research_dir / folder_name
    
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