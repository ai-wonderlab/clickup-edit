"""
Smart Retry System with Intelligent Base Image Selection
Decides whether to retry incrementally or restart from scratch
"""
from enum import Enum
from typing import Dict, List, Optional

from ..utils.logger import get_logger

logger = get_logger(__name__)


class RetryStrategy(str, Enum):
    """Retry strategy options"""
    NO_RETRY = "NO_RETRY"           # Success - no retry needed
    INCREMENTAL = "INCREMENTAL"     # Retry using edited image (small fixes)
    FULL_RESTART = "FULL_RESTART"   # Retry using original image (major issues)
    GIVE_UP = "GIVE_UP"             # Max retries exceeded


class EditComplexity(str, Enum):
    """Edit complexity classification"""
    SIMPLE = "SIMPLE"       # Single operation (move, resize, color change)
    MODERATE = "MODERATE"   # 2-3 operations
    COMPLEX = "COMPLEX"     # 4+ operations or complex transformations


class SmartRetrySystem:
    """
    Intelligent retry system that decides:
    - Whether to retry
    - Whether to use edited image (incremental) or original (restart)
    - What feedback to give to the model
    
    Decision logic:
    - Score ≥9.0: NO_RETRY (success)
    - Score 8.0-8.9 AND high confidence: INCREMENTAL (close, just tweak)
    - Score <8.0 AND <5.0: FULL_RESTART (catastrophic, start over)
    - Score 5.0-7.9: Context-dependent (check complexity)
    """
    
    def __init__(
        self,
        max_retries: int = 5,
        incremental_threshold: float = 8.0,
        catastrophic_threshold: float = 5.0
    ):
        """
        Initialize retry system.
        
        Args:
            max_retries: Maximum number of retry attempts
            incremental_threshold: Score ≥ this = incremental retry eligible
            catastrophic_threshold: Score < this = always full restart
        """
        self.max_retries = max_retries
        self.incremental_threshold = incremental_threshold
        self.catastrophic_threshold = catastrophic_threshold
        
        logger.info(
            "Smart Retry System initialized",
            extra={
                "max_retries": max_retries,
                "incremental_threshold": incremental_threshold,
                "catastrophic_threshold": catastrophic_threshold
            }
        )
    
    def determine_strategy(
        self,
        validation_result: Dict,
        edit_request: str,
        retry_count: int,
        original_image_b64: str = None,
        edited_image_b64: str = None
    ) -> Dict:
        """
        Determine the appropriate retry strategy.
        
        Args:
            validation_result: Result from StrictDualValidator
            edit_request: User's original edit request
            retry_count: Current retry count (0 = first attempt)
            original_image_b64: Base64 of original image (optional)
            edited_image_b64: Base64 of edited image (optional)
            
        Returns:
            {
                'strategy': RetryStrategy enum,
                'reason': str explaining decision,
                'retry_prompt': str to append to next edit request,
                'base_image': 'original' or 'edited',
                'issues_to_focus': list of issues for next validator
            }
        """
        decision = validation_result['decision']
        score = validation_result['avg_score']
        confidence = validation_result['confidence']
        issues = validation_result['issues']
        
        logger.info(
            f"🧠 Determining retry strategy",
            extra={
                "attempt": retry_count + 1,
                "decision": decision,
                "score": score,
                "confidence": confidence
            }
        )
        
        # Check if max retries exceeded
        if retry_count >= self.max_retries:
            logger.warning(
                f"❌ Max retries ({self.max_retries}) exceeded",
                extra={"attempts": retry_count + 1}
            )
            return self._give_up_strategy(retry_count + 1, score, issues)
        
        # Check if validation passed
        if decision == "PASS" and score >= 9.0:
            logger.info(
                f"✅ Validation passed (score: {score:.1f}/10)",
                extra={"score": score}
            )
            return self._no_retry_strategy(score)
        
        # Failed validation - determine retry approach
        
        # Classify edit complexity
        complexity = self._classify_edit_complexity(edit_request)
        
        # Assess damage level
        damage_level = self._assess_damage_level(score, issues)
        
        logger.info(
            f"📊 Analysis: complexity={complexity.value}, damage={damage_level}",
            extra={
                "complexity": complexity.value,
                "damage": damage_level,
                "score": score
            }
        )
        
        # Decision logic
        if score < self.catastrophic_threshold:
            # Catastrophic failure - always restart
            return self._full_restart_strategy(
                "Catastrophic damage detected",
                score,
                issues,
                complexity
            )
        
        elif score >= self.incremental_threshold:
            # Close to passing - incremental fix
            return self._incremental_strategy(
                "Score close to threshold, small adjustments needed",
                score,
                issues,
                complexity
            )
        
        else:
            # Moderate failure (5.0 ≤ score < 8.0)
            # Decision depends on complexity and damage type
            
            if complexity == EditComplexity.SIMPLE:
                # Simple edits shouldn't fail this badly - restart
                return self._full_restart_strategy(
                    "Simple edit should not fail this badly",
                    score,
                    issues,
                    complexity
                )
            
            elif self._has_structural_damage(issues):
                # Structural issues (logo distortion, corruption) - restart
                return self._full_restart_strategy(
                    "Structural damage detected (logo/quality issues)",
                    score,
                    issues,
                    complexity
                )
            
            elif confidence == "LOW":
                # Models disagreed - too risky to build on
                return self._full_restart_strategy(
                    "Low confidence result, restart safer",
                    score,
                    issues,
                    complexity
                )
            
            else:
                # Moderate damage, complex edit - try incremental
                return self._incremental_strategy(
                    "Moderate issues in complex edit, try incremental fix",
                    score,
                    issues,
                    complexity
                )
    
    def _no_retry_strategy(self, score: float) -> Dict:
        """Success - no retry needed"""
        return {
            'strategy': RetryStrategy.NO_RETRY,
            'reason': f'Validation passed with score {score:.1f}/10',
            'retry_prompt': None,
            'base_image': None,
            'issues_to_focus': []
        }
    
    def _incremental_strategy(
        self,
        reason: str,
        score: float,
        issues: List[str],
        complexity: EditComplexity
    ) -> Dict:
        """Retry using edited image (small fixes)"""
        
        # Build focused retry prompt
        issues_text = "\n".join(f"- {issue}" for issue in issues if issue != "No issues found")
        
        retry_prompt = f"""
RETRY INSTRUCTIONS - Incremental Fix:
Previous attempt scored {score:.1f}/10. Close but not perfect.

Issues to fix:
{issues_text}

IMPORTANT:
- The image is {score/10*100:.0f}% correct
- Make ONLY the specific changes needed to fix the issues above
- Preserve everything else exactly as-is
- Be surgical and precise
"""
        
        logger.info(
            f"➡️ Strategy: INCREMENTAL (use edited image)",
            extra={"score": score, "issues_count": len(issues)}
        )
        
        return {
            'strategy': RetryStrategy.INCREMENTAL,
            'reason': reason,
            'retry_prompt': retry_prompt.strip(),
            'base_image': 'edited',
            'issues_to_focus': issues
        }
    
    def _full_restart_strategy(
        self,
        reason: str,
        score: float,
        issues: List[str],
        complexity: EditComplexity
    ) -> Dict:
        """Retry using original image (major issues)"""
        
        # Build retry prompt with warnings
        issues_text = "\n".join(f"- {issue}" for issue in issues if issue != "No issues found")
        
        retry_prompt = f"""
RETRY INSTRUCTIONS - Full Restart:
Previous attempt scored {score:.1f}/10. Starting from original image.

Critical issues from previous attempt:
{issues_text}

CRITICAL WARNINGS:
- Pay special attention to the issues listed above
- Previous attempt had major problems - be extra careful
- Preserve logo quality pixel-perfect (no distortion)
- Preserve Greek text correctly (no unwanted tones)
- Make ONLY the requested changes, nothing else
"""
        
        logger.info(
            f"➡️ Strategy: FULL_RESTART (use original image)",
            extra={"score": score, "reason": reason}
        )
        
        return {
            'strategy': RetryStrategy.FULL_RESTART,
            'reason': reason,
            'retry_prompt': retry_prompt.strip(),
            'base_image': 'original',
            'issues_to_focus': issues
        }
    
    def _give_up_strategy(
        self,
        attempts: int,
        score: float,
        issues: List[str]
    ) -> Dict:
        """Max retries exceeded - give up"""
        
        logger.error(
            f"❌ Giving up after {attempts} attempts",
            extra={"attempts": attempts, "final_score": score}
        )
        
        return {
            'strategy': RetryStrategy.GIVE_UP,
            'reason': f'Max retries ({self.max_retries}) exceeded',
            'retry_prompt': None,
            'base_image': None,
            'issues_to_focus': issues
        }
    
    def _classify_edit_complexity(self, edit_request: str) -> EditComplexity:
        """
        Classify edit complexity based on request text.
        
        Simple: Single operation keywords
        Moderate: Multiple operations
        Complex: Many operations or complex words
        """
        request_lower = edit_request.lower()
        
        # Count operation indicators
        operation_keywords = [
            'move', 'resize', 'change', 'add', 'remove', 'replace',
            'shift', 'rotate', 'flip', 'crop', 'scale', 'adjust'
        ]
        
        operation_count = sum(1 for keyword in operation_keywords if keyword in request_lower)
        
        # Complexity indicators
        complex_indicators = [
            'multiple', 'several', 'all', 'entire', 'whole',
            'everywhere', 'throughout', 'completely', 'redesign'
        ]
        
        has_complex_indicators = any(indicator in request_lower for indicator in complex_indicators)
        
        # Word count as complexity proxy
        word_count = len(edit_request.split())
        
        # Classify
        if operation_count <= 1 and word_count < 15 and not has_complex_indicators:
            return EditComplexity.SIMPLE
        elif operation_count <= 3 and word_count < 30:
            return EditComplexity.MODERATE
        else:
            return EditComplexity.COMPLEX
    
    def _assess_damage_level(self, score: float, issues: List[str]) -> str:
        """
        Assess damage level from score and issues.
        
        Returns: "CATASTROPHIC", "SEVERE", "MODERATE", or "MINOR"
        """
        if score < 3.0:
            return "CATASTROPHIC"
        elif score < 5.0:
            return "SEVERE"
        elif score < 7.0:
            return "MODERATE"
        else:
            return "MINOR"
    
    def _has_structural_damage(self, issues: List[str]) -> bool:
        """
        Check if issues indicate structural damage.
        
        Structural damage:
        - Logo distortion, warping, corruption
        - Image corruption, quality loss
        - Major visual defects
        """
        structural_keywords = [
            'distort', 'warp', 'corrupt', 'damage', 'quality loss',
            'blur', 'artifact', 'degrade', 'merge', 'pixel'
        ]
        
        issues_text = " ".join(issues).lower()
        
        return any(keyword in issues_text for keyword in structural_keywords)