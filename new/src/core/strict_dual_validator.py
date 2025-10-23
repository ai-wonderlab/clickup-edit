"""
Strict Dual AI Validation System
Two models (Claude Sonnet 4.5 + GPT-4 Turbo Vision) with strict consensus
"""
import asyncio
from typing import Dict, List, Optional
from enum import Enum

from ..providers.openrouter import OpenRouterClient
from ..utils.logger import get_logger
from ..utils.config import get_config

logger = get_logger(__name__)


class ValidationDecision(str, Enum):
    """Validation decision states"""
    PASS = "PASS"
    FAIL = "FAIL"


class ValidationConfidence(str, Enum):
    """Confidence levels for validation"""
    HIGH = "HIGH"      # Both models agree
    MEDIUM = "MEDIUM"  # Models disagree but lean one way
    LOW = "LOW"        # Single model only or major disagreement


class StrictDualValidator:
    """
    Strict dual AI validation system.
    
    Two powerful models validate in parallel:
    - Claude Sonnet 4.5 (temp=0.0) - deterministic, precise
    - GPT-4 Turbo Vision (temp=0.0) - different perspective
    
    STRICT consensus rules:
    - Both must score ≥9.0 to PASS
    - Both must give "PASS" verdict
    - Any disagreement = FAIL with LOW confidence
    """
    
    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        validation_prompt_template: str,
        score_threshold: float = 9.0,
        both_must_pass: bool = True
    ):
        """
        Initialize strict dual validator.
        
        Args:
            openrouter_client: OpenRouter API client
            validation_prompt_template: Validation prompt template
            score_threshold: Minimum score for PASS (default: 9.0)
            both_must_pass: Whether both models must agree (default: True)
        """
        self.openrouter = openrouter_client
        self.validation_prompt_template = validation_prompt_template
        self.score_threshold = score_threshold
        self.both_must_pass = both_must_pass
        
        # Model configurations
        self.claude_model = "anthropic/claude-sonnet-4.5"
        self.gpt_model = "openai/gpt-4-turbo"  # Using GPT-4 Turbo with Vision
        
        logger.info(
            "Strict Dual Validator initialized",
            extra={
                "claude_model": self.claude_model,
                "gpt_model": self.gpt_model,
                "score_threshold": self.score_threshold,
                "both_must_pass": self.both_must_pass
            }
        )
    
    async def validate(
        self,
        original_image_bytes: bytes,
        edited_image_bytes: bytes,
        original_request: str,
        previous_issues: Optional[List[str]] = None
    ) -> Dict:
        """
        Perform strict dual validation.
        
        Args:
            original_image_bytes: Original image PNG bytes
            edited_image_bytes: Edited image PNG bytes
            original_request: User's edit request
            previous_issues: Issues from previous attempt (for retry focus)
            
        Returns:
            {
                'decision': 'PASS' or 'FAIL',
                'confidence': 'HIGH', 'MEDIUM', or 'LOW',
                'avg_score': 8.5,
                'claude': {...},
                'gpt': {...},
                'issues': [...],
                'reasoning': "..."
            }
        """
        logger.info(
            "🔍 Starting STRICT Dual AI Validation",
            extra={"has_previous_issues": bool(previous_issues)}
        )
        
        # Prepare enhanced prompt (add previous issues if retry)
        validation_prompt = self._prepare_prompt(
            original_request,
            previous_issues
        )
        
        # Run both models in parallel
        try:
            logger.info("🤖 Running parallel validation (Claude + GPT-4)...")
            
            claude_result, gpt_result = await asyncio.gather(
                self._validate_with_claude(
                    original_image_bytes,
                    edited_image_bytes,
                    validation_prompt
                ),
                self._validate_with_gpt(
                    original_image_bytes,
                    edited_image_bytes,
                    validation_prompt
                ),
                return_exceptions=True
            )
            
            # Handle exceptions
            if isinstance(claude_result, Exception):
                logger.error(
                    f"❌ Claude validation failed: {claude_result}",
                    extra={"error": str(claude_result)}
                )
                
                if isinstance(gpt_result, Exception):
                    logger.error(f"❌ GPT-4 validation also failed: {gpt_result}")
                    raise Exception("Both validators failed")
                
                # Only GPT-4 succeeded
                return self._single_model_result(gpt_result, "GPT-4")
            
            if isinstance(gpt_result, Exception):
                logger.error(
                    f"❌ GPT-4 validation failed: {gpt_result}",
                    extra={"error": str(gpt_result)}
                )
                # Only Claude succeeded
                return self._single_model_result(claude_result, "Claude")
            
            # Both succeeded - apply strict consensus
            return self._apply_strict_consensus(claude_result, gpt_result)
            
        except Exception as e:
            logger.error(
                f"❌ Validation system error: {e}",
                extra={"error": str(e)},
                exc_info=True
            )
            raise
    
    def _prepare_prompt(
        self,
        original_request: str,
        previous_issues: Optional[List[str]] = None
    ) -> str:
        """
        Prepare validation prompt with optional retry focus.
        
        If previous_issues provided, add emphasis section to make
        validators extra strict on those specific problems.
        """
        # Format base prompt
        prompt = self.validation_prompt_template.format(
            original_request=original_request
        )
        
        # Add retry focus if this is a retry attempt
        if previous_issues and len(previous_issues) > 0:
            issues_text = "\n".join(f"- {issue}" for issue in previous_issues)
            
            retry_section = f"""

═══════════════════════════════════════════════════════════════
🚨 RETRY ATTEMPT - PREVIOUS VALIDATION FAILED WITH THESE ISSUES:

{issues_text}

CRITICAL: Pay EXTRA attention to these specific problems.
Be EXTREMELY strict when checking these areas.
These issues MUST be fixed in the edited image.
═══════════════════════════════════════════════════════════════
"""
            prompt = prompt + retry_section
        
        return prompt
    
    async def _validate_with_claude(
        self,
        original_bytes: bytes,
        edited_bytes: bytes,
        prompt: str
    ) -> Dict:
        """Validate with Claude Sonnet 4.5"""
        logger.info("🤖 Validating with Claude Sonnet 4.5 (temp=0.0)...")
        
        # Use existing OpenRouter client's validate_image method
        result = await self.openrouter.validate_image(
            image_url="",  # Not used, we pass bytes
            original_image_bytes=original_bytes,
            original_request=prompt,
            model_name="claude",
            validation_prompt_template=prompt
        )
        
        logger.info(
            f"✅ Claude validation complete",
            extra={
                "score": result.score,
                "passed": result.passed,
                "issues_count": len(result.issues)
            }
        )
        
        return {
            'model': 'Claude Sonnet 4.5',
            'pass_fail': 'PASS' if result.passed else 'FAIL',
            'score': result.score,
            'issues': result.issues,
            'reasoning': result.reasoning
        }
    
    async def _validate_with_gpt(
        self,
        original_bytes: bytes,
        edited_bytes: bytes,
        prompt: str
    ) -> Dict:
        """Validate with GPT-4 Turbo Vision"""
        logger.info("🤖 Validating with GPT-4 Turbo Vision (temp=0.0)...")
        
        # Convert to base64 for GPT-4
        import base64
        original_b64 = base64.b64encode(original_bytes).decode('utf-8')
        edited_b64 = base64.b64encode(edited_bytes).decode('utf-8')
        
        # Build GPT-4 specific payload
        payload = {
            "model": self.gpt_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{original_b64}",
                                "detail": "high"
                            }
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{edited_b64}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1000,
            "temperature": 0.0
        }
        
        # Call OpenRouter
        response = await self.openrouter.client.post(
            f"{self.openrouter.base_url}/chat/completions",
            json=payload
        )
        
        self.openrouter._handle_response_errors(response)
        
        data = response.json()
        validation_text = data["choices"][0]["message"]["content"]
        
        # Parse response using existing method
        parsed = self.openrouter._parse_validation_response(
            validation_text,
            "gpt-4-turbo"
        )
        
        logger.info(
            f"✅ GPT-4 validation complete",
            extra={
                "score": parsed.score,
                "passed": parsed.passed,
                "issues_count": len(parsed.issues)
            }
        )
        
        return {
            'model': 'GPT-4 Turbo',
            'pass_fail': 'PASS' if parsed.passed else 'FAIL',
            'score': parsed.score,
            'issues': parsed.issues,
            'reasoning': parsed.reasoning
        }
    
    def _apply_strict_consensus(
        self,
        claude: Dict,
        gpt: Dict
    ) -> Dict:
        """
        Apply STRICT consensus rules.
        
        Rules:
        1. Both must give "PASS" verdict
        2. Both must score ≥9.0 (configurable threshold)
        3. Any disagreement = FAIL with LOW confidence
        
        Returns final validation result.
        """
        claude_pass = claude['pass_fail'] == 'PASS'
        gpt_pass = gpt['pass_fail'] == 'PASS'
        
        claude_score = claude['score']
        gpt_score = gpt['score']
        avg_score = (claude_score + gpt_score) / 2
        
        # Collect all unique issues
        all_issues = list(set(claude['issues'] + gpt['issues']))
        if "No issues found" in all_issues:
            all_issues.remove("No issues found")
        
        # Apply strict consensus logic
        if self.both_must_pass:
            # STRICT MODE: Both must pass AND both must score ≥threshold
            if (claude_pass and gpt_pass and 
                claude_score >= self.score_threshold and 
                gpt_score >= self.score_threshold):
                
                decision = ValidationDecision.PASS
                confidence = ValidationConfidence.HIGH
                reasoning = (
                    f"Both models agree: PASS. "
                    f"Claude: {claude_score}/10, GPT-4: {gpt_score}/10. "
                    f"High confidence validation."
                )
                final_issues = ["No issues found"]
                
            else:
                # At least one failed or scored too low
                decision = ValidationDecision.FAIL
                
                # Determine confidence based on agreement
                if claude_pass == gpt_pass:
                    # Both agree it's bad
                    confidence = ValidationConfidence.HIGH
                    reasoning = (
                        f"Both models agree: FAIL. "
                        f"Claude: {claude_score}/10, GPT-4: {gpt_score}/10."
                    )
                else:
                    # Disagreement
                    confidence = ValidationConfidence.LOW
                    reasoning = (
                        f"Models disagree (Claude: {claude['pass_fail']}, "
                        f"GPT-4: {gpt['pass_fail']}). "
                        f"Scores: {claude_score}/10, {gpt_score}/10. "
                        f"Failing due to lack of consensus."
                    )
                
                final_issues = all_issues if all_issues else [
                    "Validation threshold not met"
                ]
        
        else:
            # LENIENT MODE: At least one must pass (not recommended)
            if claude_pass or gpt_pass:
                decision = ValidationDecision.PASS
                confidence = (
                    ValidationConfidence.HIGH if (claude_pass and gpt_pass)
                    else ValidationConfidence.MEDIUM
                )
                reasoning = f"Average score: {avg_score:.1f}/10"
                final_issues = ["No issues found"]
            else:
                decision = ValidationDecision.FAIL
                confidence = ValidationConfidence.HIGH
                reasoning = f"Both models failed. Average: {avg_score:.1f}/10"
                final_issues = all_issues
        
        # Log decision
        logger.info(
            f"📊 Strict Consensus Result: {decision.value}",
            extra={
                "decision": decision.value,
                "confidence": confidence.value,
                "avg_score": avg_score,
                "claude_score": claude_score,
                "gpt_score": gpt_score,
                "claude_verdict": claude['pass_fail'],
                "gpt_verdict": gpt['pass_fail']
            }
        )
        
        return {
            'decision': decision.value,
            'confidence': confidence.value,
            'avg_score': avg_score,
            'claude': claude,
            'gpt': gpt,
            'issues': final_issues,
            'reasoning': reasoning
        }
    
    def _single_model_result(
        self,
        model_result: Dict,
        model_name: str
    ) -> Dict:
        """
        Fallback when only one model succeeded.
        Returns result with LOW confidence.
        """
        logger.warning(
            f"⚠️ Using single model result: {model_name}",
            extra={"model": model_name}
        )
        
        decision = model_result['pass_fail']
        score = model_result['score']
        
        return {
            'decision': decision,
            'confidence': ValidationConfidence.LOW.value,
            'avg_score': score,
            'claude': model_result if model_name == "Claude" else None,
            'gpt': model_result if model_name == "GPT-4" else None,
            'issues': model_result['issues'],
            'reasoning': (
                f"Single model validation only ({model_name}). "
                f"Other model failed. Low confidence result."
            )
        }