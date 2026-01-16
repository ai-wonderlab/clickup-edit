"""
Task logger for pipeline debugging.

Logs every phase of the pipeline to Supabase for analysis.
Non-blocking - failures are logged but don't affect pipeline.

Usage:
    from src.utils.task_logger import task_logger
    
    task_logger.log_phase(
        task_id="abc123",
        phase="enhancement",
        input_data={"prompt": "..."},
        output_data={"enhanced": "..."},
        duration_ms=2300
    )
"""

import time
from typing import Any, Dict, Optional
from contextlib import contextmanager

from .logger import get_logger
from .supabase_client import supabase_client

logger = get_logger(__name__)


class TaskLogger:
    """
    Non-blocking task logger.
    
    All methods fail silently - logging should never break the pipeline.
    """
    
    def __init__(self):
        self._enabled = True
    
    def log_phase(
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
    ) -> None:
        """
        Log a pipeline phase.
        
        Args:
            task_id: Unique task identifier
            phase: Phase name (parsing, enhancement, generation, validation, fallback)
            run_id: Unique identifier for this pipeline run
            model_used: Model name if applicable
            iteration: Iteration number if applicable
            input_data: Input to this phase (will be truncated)
            output_data: Output from this phase (will be truncated)
            duration_ms: Duration in milliseconds
            success: Whether phase succeeded
            error: Error message if failed
        """
        if not self._enabled:
            return
        
        try:
            # Truncate large data
            safe_input = self._truncate_data(input_data)
            safe_output = self._truncate_data(output_data)
            
            supabase_client.log_task_phase(
                task_id=task_id,
                phase=phase,
                run_id=run_id,
                model_used=model_used,
                iteration=iteration,
                input_data=safe_input,
                output_data=safe_output,
                duration_ms=duration_ms,
                success=success,
                error=error[:500] if error else None
            )
        except Exception as e:
            # Never fail - just log warning
            logger.warning(f"TaskLogger failed: {e}")
    
    def log_result(
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
        task_name: Optional[str] = None
    ) -> None:
        """Log final task result for metrics."""
        try:
            supabase_client.log_task_result(
                task_id=task_id,
                clickup_task_id=clickup_task_id,
                request=request,
                score=score,
                passed=passed,
                model_used=model_used,
                iterations=iterations,
                run_id=run_id,
                user_feedback=user_feedback,
                task_name=task_name
            )
        except Exception as e:
            logger.warning(f"Failed to log result: {e}")
    
    @contextmanager
    def phase_timer(
        self,
        task_id: str,
        phase: str,
        run_id: Optional[str] = None,
        model_used: Optional[str] = None,
        iteration: Optional[int] = None,
        input_data: Optional[Dict] = None
    ):
        """
        Context manager for timing phases.
        
        Usage:
            with task_logger.phase_timer(task_id, "enhancement", run_id=run_id) as timer:
                result = do_enhancement()
                timer.set_output({"enhanced": result})
        """
        start = time.time()
        output_holder = {"data": None, "error": None, "success": True}
        
        class Timer:
            def set_output(self, data: Dict):
                output_holder["data"] = data
            
            def set_error(self, error: str):
                output_holder["error"] = error
                output_holder["success"] = False
        
        timer = Timer()
        
        try:
            yield timer
        except Exception as e:
            output_holder["error"] = str(e)
            output_holder["success"] = False
            raise
        finally:
            duration_ms = int((time.time() - start) * 1000)
            self.log_phase(
                task_id=task_id,
                phase=phase,
                run_id=run_id,
                model_used=model_used,
                iteration=iteration,
                input_data=input_data,
                output_data=output_holder["data"],
                duration_ms=duration_ms,
                success=output_holder["success"],
                error=output_holder["error"]
            )
    
    def _truncate_data(self, data: Optional[Dict], max_size: int = 10000) -> Optional[Dict]:
        """Truncate large data to prevent DB issues."""
        if data is None:
            return None
        
        try:
            import json
            serialized = json.dumps(data)
            if len(serialized) > max_size:
                # Truncate string values
                truncated = {}
                for key, value in data.items():
                    if isinstance(value, str) and len(value) > 500:
                        truncated[key] = value[:500] + "...[truncated]"
                    else:
                        truncated[key] = value
                return truncated
            return data
        except Exception:
            return {"error": "Could not serialize data"}


# Global singleton
task_logger = TaskLogger()

