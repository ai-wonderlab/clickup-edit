"""
Central configuration manager for Image Edit Agent.

Provides unified access to prompts, parameters, and model configuration.
Supports fallback chain: Supabase → YAML → Hardcoded defaults.

Usage:
    from src.utils.config_manager import config_manager
    
    prompt = config_manager.get_prompt("P2", model_name="nano-banana-pro-edit")
    threshold = config_manager.get_parameter("VALIDATION_PASS_THRESHOLD")
    models = config_manager.get_active_models()
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from .logger import get_logger
from .supabase_client import supabase_client

logger = get_logger(__name__)


class ConfigManager:
    """
    Singleton configuration manager with graceful fallback.
    
    Priority:
    1. Supabase (if connected) - for live updates
    2. YAML file - for local/offline
    3. Hardcoded defaults - safety net
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self._initialized = True
        self._config: Dict = {}
        self._supabase = supabase_client  # Use global Supabase singleton
        self._yaml_path = Path(__file__).parent.parent.parent / "config" / "prompts.yaml"
        
        self._load_yaml()
        logger.info(
            "ConfigManager initialized",
            extra={
                "yaml_loaded": bool(self._config),
                "supabase_connected": self._supabase.is_connected
            }
        )
    
    def _load_yaml(self) -> None:
        """Load configuration from YAML file."""
        try:
            if self._yaml_path.exists():
                with open(self._yaml_path, "r", encoding="utf-8") as f:
                    self._config = yaml.safe_load(f) or {}
                logger.info(f"Loaded config from {self._yaml_path}")
            else:
                logger.warning(f"Config file not found: {self._yaml_path}")
                self._config = {}
        except Exception as e:
            logger.error(f"Failed to load YAML config: {e}")
            self._config = {}
    
    def reload(self) -> None:
        """Reload configuration from sources."""
        self._load_yaml()
        logger.info("Configuration reloaded")
    
    def get_prompt(self, prompt_id: str, **variables) -> str:
        """
        Get prompt content by ID with variable substitution.
        
        Args:
            prompt_id: Prompt identifier (P1, P2, etc.)
            **variables: Variables to substitute in the prompt
            
        Returns:
            Prompt content with variables substituted
            
        Example:
            get_prompt("P2", model_name="nano-banana-pro-edit", original_prompt="...")
        """
        # Try Supabase first
        if self._supabase.is_connected:
            content = self._supabase.get_prompt(prompt_id)
            if content:
                return self._substitute_variables(content, variables)
        
        # Fallback to YAML
        prompts = self._config.get("prompts", {})
        prompt_data = prompts.get(prompt_id, {})
        content = prompt_data.get("content", "")
        
        if not content:
            logger.warning(f"Prompt {prompt_id} not found, using hardcoded fallback")
            return self._get_hardcoded_fallback(prompt_id, variables)
        
        return self._substitute_variables(content, variables)
    
    def get_prompt_info(self, prompt_id: str) -> Optional[Dict]:
        """
        Get full prompt metadata including name, category, description.
        
        Args:
            prompt_id: Prompt identifier (P1, P2, etc.)
            
        Returns:
            Full prompt dict or None if not found
        """
        prompts = self._config.get("prompts", {})
        return prompts.get(prompt_id)
    
    def list_prompts(self, category: Optional[str] = None) -> List[str]:
        """
        List all prompt IDs, optionally filtered by category.
        
        Args:
            category: Optional category filter (enhancement, validation, building, etc.)
            
        Returns:
            List of prompt IDs
        """
        prompts = self._config.get("prompts", {})
        
        if category:
            return [
                pid for pid, pdata in prompts.items()
                if pdata.get("category") == category
            ]
        
        return list(prompts.keys())
    
    def _substitute_variables(self, content: str, variables: Dict[str, Any]) -> str:
        """Replace {variable} placeholders with actual values."""
        result = content
        for key, value in variables.items():
            placeholder = "{" + key + "}"
            result = result.replace(placeholder, str(value))
        return result
    
    def _get_hardcoded_fallback(self, prompt_id: str, variables: Dict[str, Any]) -> str:
        """
        Emergency fallback to hardcoded prompts.
        This ensures the system works even if YAML is corrupted.
        """
        fallbacks = {
            "P1": """
═══════════════════════════════════════════════════════════════
FINAL OUTPUT OVERRIDE:
═══════════════════════════════════════════════════════════════
Ignore any instructions above about warnings, recommendations, or alternatives.
Output ONLY the enhanced prompt. No meta-commentary. No markdown headers.
Just the pure editing instructions.""",
            
            "P6": """Validate this edit.

USER REQUEST: {original_request}

Compare IMAGE 1 (original) with IMAGE 2 (edited).
Return ONLY JSON.""",
            
            "P7": """Validate this edit.

USER REQUEST: {original_request}

Compare IMAGES 1-{num_originals} (originals/inputs) with FINAL IMAGE (edited result).
Verify ALL input images are properly incorporated in the output.
Return ONLY JSON.""",

            "P11": """Adapt this image to {dimension} aspect ratio.
Keep ALL content identical: same person, same text, same logo, same colors, same style.
Reframe/expand the composition to fill the new {dimension} canvas edge-to-edge.
Do NOT add borders or letterboxing.""",
        }
        
        # Try file fallback for specific prompts
        file_fallback = self._get_file_fallback(prompt_id)
        if file_fallback:
            return self._substitute_variables(file_fallback, variables)
        
        content = fallbacks.get(prompt_id, f"[MISSING PROMPT: {prompt_id}]")
        return self._substitute_variables(content, variables)
    
    def _get_file_fallback(self, prompt_id: str) -> Optional[str]:
        """
        Load prompt from file if not in Supabase/YAML.
        This is the final fallback for large prompts stored in files.
        """
        config_dir = Path(__file__).parent.parent.parent / "config"
        
        file_mappings = {
            "P4": config_dir / "prompts" / "validation_prompt.txt",
            "P5": config_dir / "prompts" / "validation_branded_creative.txt",
            "P8": config_dir / "prompts" / "brand_analyzer_prompt.txt",
            "P17": config_dir / "shared" / "fonts.md",
        }
        
        # Handle deep research prompts (DR_{model}_activation, DR_{model}_research)
        if prompt_id.startswith("DR_") and "_" in prompt_id[3:]:
            parts = prompt_id[3:].rsplit("_", 1)  # Split from right
            if len(parts) == 2:
                model_name, prompt_type = parts
                if prompt_type == "activation":
                    file_mappings[prompt_id] = config_dir / "deep_research" / model_name / "activation.txt"
                elif prompt_type == "research":
                    file_mappings[prompt_id] = config_dir / "deep_research" / model_name / "research.md"
        
        file_path = file_mappings.get(prompt_id)
        if file_path and file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
                logger.debug(f"Loaded {prompt_id} from file fallback: {file_path}")
                return content
            except Exception as e:
                logger.warning(f"Failed to load {prompt_id} from file: {e}")
        
        return None
    
    def get_validation_prompt(self, task_type: str = "SIMPLE_EDIT") -> str:
        """
        Get validation system prompt by task type.
        
        Args:
            task_type: SIMPLE_EDIT or BRANDED_CREATIVE
            
        Returns:
            Validation prompt content
        """
        prompt_id = "P5" if task_type == "BRANDED_CREATIVE" else "P4"
        return self.get_prompt(prompt_id)
    
    def get_fonts_guide(self) -> str:
        """
        Get fonts translation guide.
        
        Returns:
            Fonts guide content or empty string
        """
        content = self.get_prompt("P17")
        return content if content != "[MISSING PROMPT: P17]" else ""
    
    def get_deep_research(self, model_name: str) -> Dict[str, str]:
        """
        Get deep research files for a model.
        
        Args:
            model_name: Model name (e.g., 'nano-banana-pro-edit')
            
        Returns:
            Dict with 'activation' and 'research' content
        """
        activation = self.get_prompt(f"DR_{model_name}_activation")
        research = self.get_prompt(f"DR_{model_name}_research")
        
        # Check if we got valid content
        if activation.startswith("[MISSING PROMPT:"):
            activation = ""
        if research.startswith("[MISSING PROMPT:"):
            research = ""
        
        return {
            "activation": activation,
            "research": research,
        }
    
    def get_brand_analyzer_prompt(self) -> str:
        """
        Get brand analyzer system prompt.
        
        Returns:
            Brand analyzer prompt content
        """
        return self.get_prompt("P8")
    
    def get_parameter(self, key: str, default: Any = None) -> Any:
        """
        Get parameter value with type conversion.
        
        Args:
            key: Parameter key (e.g., "VALIDATION_PASS_THRESHOLD")
            default: Default value if not found
            
        Returns:
            Parameter value with correct type
        """
        # Try Supabase first
        if self._supabase.is_connected:
            value = self._supabase.get_parameter(key)
            if value is not None:
                return value
        
        # Try YAML
        params = self._config.get("parameters", {})
        param_data = params.get(key, {})
        
        if not param_data:
            # Fallback to environment variable
            env_value = os.getenv(key)
            if env_value is not None:
                return self._convert_type(env_value, "auto")
            return default
        
        value = param_data.get("value", default)
        param_type = param_data.get("type", "string")
        
        return self._convert_type(value, param_type)
    
    def get_parameter_info(self, key: str) -> Optional[Dict]:
        """
        Get full parameter metadata including min, max, description.
        
        Args:
            key: Parameter key
            
        Returns:
            Full parameter dict or None if not found
        """
        params = self._config.get("parameters", {})
        return params.get(key)
    
    def list_parameters(self) -> List[str]:
        """
        List all parameter keys.
        
        Returns:
            List of parameter keys
        """
        params = self._config.get("parameters", {})
        return list(params.keys())
    
    def _convert_type(self, value: Any, param_type: str) -> Any:
        """Convert value to specified type."""
        if value is None:
            return None
        
        try:
            if param_type == "int":
                return int(value)
            elif param_type == "float":
                return float(value)
            elif param_type == "bool" or param_type == "boolean":
                if isinstance(value, bool):
                    return value
                return str(value).lower() in ("true", "1", "yes")
            elif param_type == "auto":
                # Try to auto-detect
                try:
                    return int(value)
                except ValueError:
                    try:
                        return float(value)
                    except ValueError:
                        if str(value).lower() in ("true", "false"):
                            return str(value).lower() == "true"
                        return value
            else:
                return str(value)
        except (ValueError, TypeError):
            return value
    
    def get_active_models(self) -> List[str]:
        """Get list of active model names sorted by priority."""
        # Try Supabase first
        if self._supabase.is_connected:
            models = self._supabase.get_active_models()
            if models:
                return models
        
        # Fallback to YAML
        models = self._config.get("models", [])
        active = [m for m in models if m.get("is_active", False)]
        active.sort(key=lambda m: m.get("priority", 99))
        return [m["name"] for m in active]
    
    def get_all_models(self) -> List[Dict]:
        """Get all models with their full configuration."""
        return self._config.get("models", [])
    
    def get_model_config(self, model_name: str) -> Optional[Dict]:
        """Get full configuration for a specific model."""
        models = self._config.get("models", [])
        for model in models:
            if model.get("name") == model_name:
                return model
        return None
    
    def is_model_active(self, model_name: str) -> bool:
        """Check if a model is active."""
        model = self.get_model_config(model_name)
        return model.get("is_active", False) if model else False
    
    @property
    def is_supabase_connected(self) -> bool:
        """Check if Supabase is connected."""
        return self._supabase.is_connected
    
    @property
    def config_path(self) -> Path:
        """Get the path to the YAML config file."""
        return self._yaml_path
    
    def get_raw_config(self) -> Dict:
        """Get the raw configuration dict (for debugging)."""
        return self._config.copy()


# Global singleton instance
config_manager = ConfigManager()

