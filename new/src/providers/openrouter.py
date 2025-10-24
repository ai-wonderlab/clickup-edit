"""OpenRouter API client for Claude and Gemini models."""

import json
import base64
from typing import Dict, Any, Optional
import httpx

from .base import BaseProvider
from ..utils.logger import get_logger
from ..utils.errors import ProviderError, AuthenticationError, RateLimitError
from ..utils.retry import retry_async
from ..models.schemas import ValidationResult
from ..models.enums import ValidationStatus

logger = get_logger(__name__)


class OpenRouterClient(BaseProvider):
    """Client for OpenRouter API (Claude + Gemini)."""
    
    def __init__(self, api_key: str, timeout: float = 120.0):
        """
        Initialize OpenRouter client.
        
        Args:
            api_key: OpenRouter API key
            timeout: Request timeout in seconds
        """
        super().__init__(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=timeout,
        )
    
    def _get_default_headers(self) -> dict:
        """Get default headers for OpenRouter requests."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://image-edit-agent.com",  # Required by OpenRouter
            "X-Title": "Image Edit Agent",  # Optional, for OpenRouter dashboard
        }
    
    @retry_async(max_attempts=3, exceptions=(httpx.RequestError, ProviderError))
    async def enhance_prompt(
        self,
        original_prompt: str,
        model_name: str,
        deep_research: str,
        original_image_bytes: Optional[bytes] = None,
        cache_enabled: bool = True,
    ) -> str:
        """Enhance user prompt using Claude with system/user split."""
        self._ensure_client()
        
        try:
            # ═══════════════════════════════════════════════════════════
            # SYSTEM PROMPT = Entire deep research (activation + research)
            # ═══════════════════════════════════════════════════════════
            system_prompt = deep_research  # ~8K tokens
            
            # ═══════════════════════════════════════════════════════════
            # USER PROMPT = Simple enhancement request
            # ═══════════════════════════════════════════════════════════
            user_text = f"""Enhance this image editing request for {model_name}:

{original_prompt}

Output: Enhanced prompt only."""
            
            # ═══════════════════════════════════════════════════════════
            # BUILD USER CONTENT (text + optional image)
            # ═══════════════════════════════════════════════════════════
            user_content = [
                {
                    "type": "text",
                    "text": user_text
                }
            ]
            
            # Add image if provided
            if original_image_bytes:
                img_b64 = base64.b64encode(original_image_bytes).decode('utf-8')
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_b64}"
                    }
                })
            
            # ═══════════════════════════════════════════════════════════
            # BUILD MESSAGES (system/user split)
            # ═══════════════════════════════════════════════════════════
            messages = [
                {
                    "role": "system",
                    "content": system_prompt  # ✅ All research & activation
                },
                {
                    "role": "user",
                    "content": user_content  # ✅ Simple request + image
                }
            ]
            
            # ═══════════════════════════════════════════════════════════
            # BUILD PAYLOAD with LOCKED PARAMETERS
            # ═══════════════════════════════════════════════════════════
            payload = {
                "model": "anthropic/claude-sonnet-4.5",
                "messages": messages,
                "max_tokens": 2000,
                # temperature removed - defaults to 1.0 (required for thinking)
                
                # ✅ ADD THINKING MODE
                "reasoning": {
                    "effort": "medium"  # Medium for enhancement (faster)
                },
                
                # ✅ LOCK PROVIDER
                "provider": {
                    "order": ["Anthropic"],
                    "allow_fallbacks": False
                }
            }
            
            # ═══════════════════════════════════════════════════════════
            # API CALL
            # ═══════════════════════════════════════════════════════════
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=None
            )
            
            self._handle_response_errors(response)
            
            data = response.json()
            
            # ═══════════════════════════════════════════════════════════
            # VERIFY NO FALLBACK
            # ═══════════════════════════════════════════════════════════
            actual_model = data.get("model", "unknown")
            
            if actual_model != "anthropic/claude-sonnet-4.5":
                logger.warning(
                    f"Provider fallback in enhancement: {actual_model}",
                    extra={
                        "expected": "anthropic/claude-sonnet-4.5",
                        "actual": actual_model,
                        "image_model": model_name
                    }
                )
            
            logger.info(
                "Enhancement complete",
                extra={
                    "model_requested": "anthropic/claude-sonnet-4.5",
                    "model_actual": actual_model,
                    "image_model": model_name,
                    "has_image": original_image_bytes is not None
                }
            )
            
            # ═══════════════════════════════════════════════════════════
            # RETURN ENHANCED PROMPT
            # ═══════════════════════════════════════════════════════════
            enhanced = data["choices"][0]["message"]["content"]
            return enhanced.strip()
            
        except Exception as e:
            logger.error(
                f"Enhancement failed: {e}",
                extra={
                    "model": model_name,
                    "error": str(e)
                },
                exc_info=True
            )
            
            # Fallback: return original prompt
            logger.warning(f"Returning original prompt due to enhancement failure")
            return original_prompt
    
    @retry_async(max_attempts=3, exceptions=(httpx.RequestError, ProviderError))
    async def validate_image(
        self,
        image_url: str,  # Edited image (CloudFront URL)
        original_image_bytes: bytes,  # Original image (PNG bytes)
        original_request: str,  # User's request
        model_name: str,  # Which model generated it
        validation_prompt_template: str  # ✅ This becomes SYSTEM prompt
    ) -> ValidationResult:
        """Validate edited image using Claude with system/user split."""
        self._ensure_client()
        
        try:
            # ═══════════════════════════════════════════════════════════
            # SYSTEM PROMPT = Entire validation prompt (290 lines)
            # ═══════════════════════════════════════════════════════════
            system_prompt = validation_prompt_template
            
            # ═══════════════════════════════════════════════════════════
            # USER PROMPT = Simple task
            # ═══════════════════════════════════════════════════════════
            user_text = f"""Validate this edit.

USER REQUEST: {original_request}

Compare IMAGE 1 (original) with IMAGE 2 (edited).
Return ONLY JSON."""
            
            # ═══════════════════════════════════════════════════════════
            # PREPARE IMAGES
            # ═══════════════════════════════════════════════════════════
            # Original image: bytes → base64
            original_b64 = base64.b64encode(original_image_bytes).decode('utf-8')
            original_data_url = f"data:image/png;base64,{original_b64}"
            
            # Edited image: download from URL
            logger.info("📥 Downloading edited image for validation")
            async with httpx.AsyncClient(timeout=30.0) as download_client:
                edited_response = await download_client.get(image_url)
                edited_response.raise_for_status()
                edited_bytes = edited_response.content
            
            edited_b64 = base64.b64encode(edited_bytes).decode('utf-8')
            edited_data_url = f"data:image/png;base64,{edited_b64}"
            
            logger.info("✅ Both images prepared for validation")
            
            # ═══════════════════════════════════════════════════════════
            # BUILD MESSAGES (system/user split)
            # ═══════════════════════════════════════════════════════════
            messages = [
                {
                    "role": "system",
                    "content": system_prompt  # ✅ All validation instructions
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_text
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": original_data_url
                            }
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": edited_data_url
                            }
                        }
                    ]
                }
            ]
            
            # ═══════════════════════════════════════════════════════════
            # BUILD PAYLOAD with LOCKED PARAMETERS
            # ═══════════════════════════════════════════════════════════
            payload = {
                "model": "anthropic/claude-sonnet-4.5",
                "messages": messages,
                "max_tokens": 2000,
                # temperature removed - defaults to 1.0 (required for thinking)
                
                # ✅ LOCK PROVIDER (prevent fallbacks)
                "provider": {
                    "order": ["Anthropic"],
                    "allow_fallbacks": False
                }
            }
            
            # ═══════════════════════════════════════════════════════════
            # DEBUG LOGGING
            # ═══════════════════════════════════════════════════════════
            logger.error(
                f"🔍 DEBUG VALIDATION REQUEST for {model_name}",
                extra={
                    "model": payload["model"],
                    "original_size_kb": len(original_b64) * 0.75 / 1024,
                    "edited_size_kb": len(edited_b64) * 0.75 / 1024,
                    "system_prompt_length": len(system_prompt),
                    "max_tokens": payload["max_tokens"],
                    "has_reasoning": "reasoning" in payload
                }
            )
            
            # ═══════════════════════════════════════════════════════════
            # API CALL
            # ═══════════════════════════════════════════════════════════
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            
            self._handle_response_errors(response)
            
            data = response.json()
            
            # ═══════════════════════════════════════════════════════════
            # VERIFY NO FALLBACK
            # ═══════════════════════════════════════════════════════════
            actual_model = data.get("model", "unknown")
            
            logger.info(
                "Validation complete",
                extra={
                    "model_requested": "anthropic/claude-sonnet-4.5",
                    "model_actual": actual_model,
                    "provider_locked": True,
                    "image_model": model_name
                }
            )
            
            # Alert if fallback occurred
            if actual_model != "anthropic/claude-sonnet-4.5":
                logger.error(
                    "🚨 PROVIDER FALLBACK DETECTED",
                    extra={
                        "expected": "anthropic/claude-sonnet-4.5",
                        "actual": actual_model
                    }
                )
            
            # ═══════════════════════════════════════════════════════════
            # PARSE JSON RESPONSE
            # ═══════════════════════════════════════════════════════════
            content = data["choices"][0]["message"]["content"]
            
            # Strip markdown code blocks if present
            import re
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```\s*$', '', content)
            content = content.strip()
            
            # Parse JSON
            result_data = json.loads(content)
            
            # Validate structure
            required_keys = ["pass_fail", "score", "issues", "reasoning"]
            if not all(key in result_data for key in required_keys):
                raise ValueError(f"Missing required keys: {required_keys}")
            
            # Validate pass_fail value
            if result_data["pass_fail"] not in ["PASS", "FAIL"]:
                raise ValueError(f"Invalid pass_fail value: {result_data['pass_fail']}")
            
            # Build result
            return ValidationResult(
                model_name=model_name,
                passed=(result_data["pass_fail"] == "PASS"),
                score=result_data["score"],
                issues=result_data["issues"],
                reasoning=result_data["reasoning"],
                status=ValidationStatus.PASS if result_data["pass_fail"] == "PASS" else ValidationStatus.FAIL,
            )
            
        except json.JSONDecodeError as e:
            logger.error(
                f"JSON parse error: {e}",
                extra={
                    "raw_content": content[:500] if 'content' in locals() else "N/A",
                    "model": model_name
                }
            )
            
            return ValidationResult(
                model_name=model_name,
                passed=False,
                score=0,
                issues=[f"JSON parse error: {str(e)}"],
                reasoning="Validation response was not valid JSON",
                status=ValidationStatus.ERROR,
            )
            
        except Exception as e:
            logger.error(
                f"Validation failed: {e}",
                extra={
                    "model": model_name,
                    "error": str(e)
                },
                exc_info=True
            )
            
            return ValidationResult(
                model_name=model_name,
                passed=False,
                score=0,
                issues=[f"Validation error: {str(e)}"],
                reasoning="Validation process failed",
                status=ValidationStatus.ERROR,
            )
    
    def _parse_validation_response(
        self,
        validation_text: str,
        model_name: str,
    ) -> ValidationResult:
        """
        Parse validation response into structured result.
        
        Args:
            validation_text: Raw validation text from API
            model_name: Model being validated
            
        Returns:
            ValidationResult
        """
        import re
        
        try:
            # Normalize line endings and whitespace
            json_text = validation_text.strip()
            
            # Remove markdown code blocks if present
            if '```' in json_text:
                # Remove opening ```json or ```
                json_text = re.sub(r'^```(?:json)?\s*', '', json_text, flags=re.MULTILINE)
                # Remove closing ```
                json_text = re.sub(r'\s*```\s*$', '', json_text, flags=re.MULTILINE)
                json_text = json_text.strip()

            logger.debug(f"After markdown strip: {json_text[:200]}")

            # Extract JSON object - find OUTERMOST braces
            brace_count = 0
            start_idx = -1
            end_idx = -1

            for i, char in enumerate(json_text):
                if char == '{':
                    if brace_count == 0:
                        start_idx = i
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i
                        break

            if start_idx != -1 and end_idx != -1:
                json_text = json_text[start_idx:end_idx+1]
                logger.debug(f"Extracted JSON length: {len(json_text)} chars")
            else:
                logger.error(
                    f"No valid JSON object found. Brace count: {brace_count}, "
                    f"Start: {start_idx}, End: {end_idx}. "
                    f"Response preview: {validation_text[:500]}"
                )
                
                # ATTEMPT RECOVERY: Try to parse whatever we have
                if start_idx != -1:
                    logger.warning("Attempting to recover incomplete JSON...")
                    # Extract what we have and try to close it
                    partial = json_text[start_idx:]
                    
                    # Count open braces/brackets to close properly
                    open_braces = partial.count('{') - partial.count('}')
                    open_brackets = partial.count('[') - partial.count(']')
                    
                    # Close incomplete strings if needed
                    if partial.count('"') % 2 == 1:
                        partial += '"'
                    
                    # Close arrays and objects
                    for _ in range(open_brackets):
                        partial += ']'
                    for _ in range(open_braces):
                        partial += '}'
                    
                    json_text = partial
                    logger.info(f"Recovery attempt - closed {open_brackets} arrays, {open_braces} objects")
                else:
                    raise ValueError("Response does not contain JSON object")
            
            logger.debug(
                f"Parsing validation JSON",
                extra={"json_preview": json_text[:200]}
            )
            
            # Parse JSON
            data = json.loads(json_text)

            # ✅ DEFENSIVE NORMALIZATION - Handle Gemini format variations
            data = self._normalize_gemini_response(data)

            # Extract and validate fields
            pass_fail = data.get("pass_fail", "FAIL").upper()
            score = int(data.get("score", 0))
            issues = data.get("issues", ["Parse error: no issues found"])
            reasoning = data.get("reasoning", "")
            
            # Validate pass_fail matches score
            expected_pass = "PASS" if score >= 8 else "FAIL"
            if pass_fail != expected_pass:
                logger.warning(
                    f"Inconsistent validation: pass_fail={pass_fail} but score={score}",
                    extra={"score": score, "pass_fail": pass_fail}
                )
                # Override with score-based logic
                pass_fail = expected_pass
            
            # Ensure issues is a list
            if not isinstance(issues, list):
                issues = [str(issues)]
            
            # If no issues but failed, add default
            if not issues and pass_fail == "FAIL":
                issues = ["Validation failed but no specific issues provided"]
            
            # Clean up "No issues found" for passed results
            if pass_fail == "PASS" and issues == ["No issues found"]:
                issues = []
            
            logger.info(
                f"Validation parsed successfully",
                extra={
                    "passed": pass_fail == "PASS",
                    "score": score,
                    "issues_count": len(issues)
                }
            )
            
            return ValidationResult(
                model_name=model_name,
                passed=pass_fail == "PASS",
                score=score,
                issues=issues if issues else ["None"],
                reasoning=reasoning or validation_text,
                status=ValidationStatus.PASS if pass_fail == "PASS" else ValidationStatus.FAIL,
            )
            
        except json.JSONDecodeError as e:
            logger.error(
                f"Failed to parse JSON validation response: {e}",
                extra={
                    "response_preview": validation_text[:500],
                    "error": str(e)
                }
            )
            
            # Fallback: try to extract score from malformed JSON
            score_match = re.search(r'"?score"?\s*:\s*(\d+)', validation_text)
            score = int(score_match.group(1)) if score_match else 0
            
            return ValidationResult(
                model_name=model_name,
                passed=False,
                score=score,
                issues=["Failed to parse validation JSON response"],
                reasoning=validation_text[:200],
                status=ValidationStatus.ERROR,
            )
        
        except Exception as e:
            logger.error(
                f"Unexpected error parsing validation: {e}",
                extra={"error": str(e), "type": type(e).__name__}
            )
            return ValidationResult(
                model_name=model_name,
                passed=False,
                score=0,
                issues=[f"Parse error: {str(e)}"],
                reasoning="",
                status=ValidationStatus.ERROR,
            )
    
    def _normalize_gemini_response(self, data: dict) -> dict:
        """
        Normalize Gemini's response to handle format variations.
        
        Handles:
        - "10/10" → 10
        - "8.0" → 8
        - "score: 8" → 8
        
        Args:
            data: Raw parsed JSON
            
        Returns:
            Normalized dictionary
        """
        score = data.get("score")
        
        # Handle "10/10" format
        if isinstance(score, str) and "/" in score:
            score = int(score.split("/")[0].strip())
            logger.debug(f"Normalized score from fraction: {data.get('score')} → {score}")
        
        # Handle string numbers
        elif isinstance(score, str):
            score = int(float(score))  # Handle "8.0" or "8"
            logger.debug(f"Normalized score from string: {data.get('score')} → {score}")
        
        # Handle float
        elif isinstance(score, float):
            score = int(score)
            logger.debug(f"Normalized score from float: {data.get('score')} → {score}")
        
        # Clamp to valid range
        if score is not None:
            score = max(0, min(10, score))
            data["score"] = score
        
        return data

    def _handle_response_errors(self, response: httpx.Response):
        """Handle HTTP response errors."""
        if response.status_code == 401:
            raise AuthenticationError("openrouter")
        elif response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitError(
                "openrouter",
                int(retry_after) if retry_after else None
            )
        elif response.status_code >= 400:
            try:
                error_data = response.json()
                error_message = error_data.get("error", {}).get("message", response.text)
                
                # ✅ FULL ERROR DETAILS
                logger.error(
                    f"🔥 FULL ERROR DETAILS:\n"
                    f"Status: {response.status_code}\n"
                    f"Error: {json.dumps(error_data, indent=2)}\n"
                    f"Raw: {response.text}"
                )
                
            except:
                error_message = response.text
            
            raise ProviderError(
                "openrouter",
                error_message,
                response.status_code
            )