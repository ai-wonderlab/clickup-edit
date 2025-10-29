"""Hybrid fallback component for triggering human review."""

from typing import List

from ..providers.clickup import ClickUpClient
from ..models.schemas import ValidationResult
from ..utils.logger import get_logger

logger = get_logger(__name__)


class HybridFallback:
    """Handles hybrid fallback to human review after automated failures."""
    
    def __init__(self, clickup_client: ClickUpClient):
        """
        Initialize hybrid fallback handler.
        
        Args:
            clickup_client: ClickUp API client
        """
        self.client = clickup_client
    
    def format_issues(self, failed_results: List[ValidationResult]) -> str:
        """
        Format validation issues into human-readable summary.
        
        Args:
            failed_results: List of failed validation results
            
        Returns:
            Formatted issues string
        """
        all_issues = []
        
        for result in failed_results:
            if not result.passed:
                for issue in result.issues:
                    if issue and issue.lower() not in ["none", "n/a"]:
                        all_issues.append(f"[{result.model_name}] {issue}")
        
        # Deduplicate while preserving model context
        unique_issues = list(set(all_issues))
        
        if not unique_issues:
            return "- Quality standards not met (specific issues not captured)"
        
        return "\n".join(f"- {issue}" for issue in unique_issues)
    
    async def trigger_human_review(
        self,
        task_id: str,
        original_prompt: str,
        iterations_attempted: int,
        failed_results: List[ValidationResult],
    ):
        """
        Trigger human review by updating ClickUp task.
        
        Args:
            task_id: ClickUp task ID
            original_prompt: Original user request
            iterations_attempted: Number of iterations attempted
            failed_results: List of failed validation results
        """
        logger.info(
            "Triggering hybrid fallback",
            extra={
                "task_id": task_id,
                "iterations": iterations_attempted,
                "failures": len(failed_results),
            }
        )
        
        # Format issues for human review
        issues_summary = self.format_issues(failed_results)
        
        # Create detailed comment
        comment = f"""🤖 **AI Agent - Hybrid Fallback Triggered**

**Status:** Requires Human Review

**Summary:**
The AI agent attempted {iterations_attempted} iterations but could not produce an edit that meets quality standards.

**Original Request:**
```
{original_prompt}
```

**Issues Detected:**
{issues_summary}

**Models Attempted:**
{', '.join(set(r.model_name for r in failed_results))}

**Next Steps:**
1. Review the original request for clarity
2. Check if requirements are feasible for automated editing
3. Consider manual editing or revised requirements
4. Update task status when resolved

---
*Automated message from Image Edit Agent*
"""
        
        try:
            # ✅ NEW: Use config value for status name
            from ..utils.config import get_config
            config = get_config()
            
            # Update task status
            await self.client.update_task_status(
                task_id=task_id,
                status=config.clickup_status_needs_review,
                comment=comment,
            )
            
            logger.info(
                "Hybrid fallback triggered successfully",
                extra={"task_id": task_id}
            )
            
        except Exception as e:
            logger.error(
                f"Failed to trigger hybrid fallback: {e}",
                extra={
                    "task_id": task_id,
                    "error": str(e),
                }
            )
            # Don't raise - fallback notification failure shouldn't crash the system
