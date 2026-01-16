"""
Supabase client for Image Edit Agent.

Handles:
- Connection management with graceful failure
- CRUD operations for prompts, parameters, models
- Realtime subscriptions for hot-reload (future)

Environment variables:
- SUPABASE_URL
- SUPABASE_ANON_KEY
"""

import os
from typing import Any, Dict, List, Optional

from .logger import get_logger

logger = get_logger(__name__)

# Lazy import to avoid errors if supabase not installed
_supabase_client = None


def _get_supabase():
    """Lazy initialization of Supabase client."""
    global _supabase_client
    
    if _supabase_client is not None:
        return _supabase_client
    
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    
    if not url or not key:
        logger.info("Supabase not configured (SUPABASE_URL or SUPABASE_ANON_KEY missing)")
        return None
    
    try:
        from supabase import create_client
        _supabase_client = create_client(url, key)
        logger.info("Supabase client initialized successfully")
        return _supabase_client
    except ImportError:
        logger.warning("supabase package not installed")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Supabase: {e}")
        return None


class SupabaseClient:
    """
    Wrapper for Supabase operations with graceful degradation.
    
    All methods return None on failure (never raise exceptions).
    Caller should handle None by falling back to YAML/defaults.
    """
    
    def __init__(self):
        self._client = None
        self._connected = False
        self._initialize()
    
    def _initialize(self):
        """Initialize connection."""
        self._client = _get_supabase()
        self._connected = self._client is not None
    
    @property
    def is_connected(self) -> bool:
        """Check if Supabase is connected."""
        return self._connected
    
    # ==================== PROMPTS ====================
    
    def get_prompt(self, prompt_id: str) -> Optional[str]:
        """
        Get prompt content by ID.
        
        Args:
            prompt_id: Prompt identifier (P1, P2, etc.)
            
        Returns:
            Prompt content or None if not found/error
        """
        if not self._client:
            return None
        
        try:
            result = self._client.table("prompts")\
                .select("content")\
                .eq("prompt_id", prompt_id)\
                .single()\
                .execute()
            
            if result.data:
                return result.data.get("content")
            return None
        except Exception as e:
            logger.warning(f"Failed to get prompt {prompt_id} from Supabase: {e}")
            return None
    
    def get_all_prompts(self) -> Optional[List[Dict]]:
        """Get all prompts."""
        if not self._client:
            return None
        
        try:
            result = self._client.table("prompts")\
                .select("*")\
                .execute()
            return result.data
        except Exception as e:
            logger.warning(f"Failed to get prompts from Supabase: {e}")
            return None
    
    def update_prompt(self, prompt_id: str, content: str) -> bool:
        """
        Update prompt content.
        
        Args:
            prompt_id: Prompt identifier
            content: New content
            
        Returns:
            True if successful
        """
        if not self._client:
            return False
        
        try:
            self._client.table("prompts")\
                .update({"content": content})\
                .eq("prompt_id", prompt_id)\
                .execute()
            logger.info(f"Updated prompt {prompt_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update prompt {prompt_id}: {e}")
            return False
    
    # ==================== PARAMETERS ====================
    
    def get_parameter(self, key: str) -> Optional[Any]:
        """
        Get parameter value.
        
        Args:
            key: Parameter key
            
        Returns:
            Parameter value (auto-converted) or None
        """
        if not self._client:
            return None
        
        try:
            result = self._client.table("parameters")\
                .select("value, type")\
                .eq("key", key)\
                .single()\
                .execute()
            
            if result.data:
                value = result.data.get("value")
                param_type = result.data.get("type", "string")
                return self._convert_type(value, param_type)
            return None
        except Exception as e:
            logger.warning(f"Failed to get parameter {key} from Supabase: {e}")
            return None
    
    def _convert_type(self, value: Any, param_type: str) -> Any:
        """Convert value to specified type."""
        if value is None:
            return None
        try:
            if param_type == "int":
                return int(value)
            elif param_type == "float":
                return float(value)
            elif param_type in ("bool", "boolean"):
                return str(value).lower() in ("true", "1", "yes")
            return str(value)
        except (ValueError, TypeError):
            return value
    
    # ==================== MODELS ====================
    
    def get_active_models(self) -> Optional[List[str]]:
        """Get list of active model names sorted by priority."""
        if not self._client:
            return None
        
        try:
            result = self._client.table("models")\
                .select("name")\
                .eq("is_active", True)\
                .order("priority")\
                .execute()
            
            if result.data:
                return [m["name"] for m in result.data]
            return None
        except Exception as e:
            logger.warning(f"Failed to get models from Supabase: {e}")
            return None
    
    # ==================== TASK RESULTS ====================
    
    def log_task_result(
        self,
        task_id: str,
        clickup_task_id: str,
        request: str,
        score: int,
        passed: bool,
        model_used: str,
        iterations: int,
        run_id: Optional[str] = None,
        user_feedback: Optional[str] = None,
        user_notes: Optional[str] = None
    ) -> bool:
        """Log task result for metrics."""
        if not self._client:
            return False
        
        try:
            self._client.table("task_results").insert({
                "task_id": task_id,
                "run_id": run_id,
                "clickup_task_id": clickup_task_id,
                "request": request[:1000] if request else None,  # Truncate
                "score": score,
                "passed": passed,
                "model_used": model_used,
                "iterations": iterations,
                "user_feedback": user_feedback,
                "user_notes": user_notes
            }).execute()
            return True
        except Exception as e:
            logger.warning(f"Failed to log task result: {e}")
            return False
    
    # ==================== TASK LOGS ====================
    
    def log_task_phase(
        self,
        task_id: str,
        phase: str,
        run_id: Optional[str] = None,
        model_used: Optional[str] = None,
        iteration: Optional[int] = None,
        input_data: Optional[Dict] = None,
        output_data: Optional[Dict] = None,
        duration_ms: Optional[int] = None,
        success: bool = True,
        error: Optional[str] = None
    ) -> bool:
        """Log individual pipeline phase for debugging."""
        if not self._client:
            return False
        
        try:
            self._client.table("task_logs").insert({
                "task_id": task_id,
                "run_id": run_id,
                "phase": phase,
                "model_used": model_used,
                "iteration": iteration,
                "input": input_data,
                "output": output_data,
                "duration_ms": duration_ms,
                "success": success,
                "error": error
            }).execute()
            return True
        except Exception as e:
            logger.warning(f"Failed to log task phase: {e}")
            return False


# Global singleton instance
supabase_client = SupabaseClient()

