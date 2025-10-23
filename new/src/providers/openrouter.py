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
        original_image_bytes: Optional[bytes] = None,  # ✅ Receive bytes not URL
        cache_enabled: bool = True,
    ) -> str:
        """
        Enhance a prompt using Claude Sonnet 4.5.
        
        Args:
            original_prompt: Original user prompt
            model_name: Target image model name
            deep_research: Combined activation + research content
            cache_enabled: Enable prompt caching
            
        Returns:
            Enhanced prompt string
            
        Raises:
            ProviderError: If API request fails
        """
        self._ensure_client()
        
        # Construct enhancement system prompt
        system_prompt = f"""You are an expert prompt optimizer for the {model_name} image editing model.

        === CRITICAL OPERATIONAL RULES ===
        1. OUTPUT FORMAT: Return ONLY the enhanced prompt text - nothing else
        2. NO ANALYSIS: Do not explain limitations, concerns, or alternatives
        3. NO QUESTIONS: Do not ask the user anything
        4. NO REFUSALS: Always enhance the prompt, even if the request seems difficult
        5. NO PREAMBLES: Do not write "Here's the enhanced prompt:" or similar
        6. NO POSTAMBLES: Do not add notes, warnings, or recommendations
        7. JUST THE PROMPT: Pure enhanced prompt text only

        If you output ANYTHING other than the enhanced prompt, the system will fail.

        {deep_research}

        Your task: Transform the user's edit request into an optimized prompt that maximizes success rate.

        Enhancement requirements:
        1. Preserve the user's core intent exactly
        2. Add explicit preservation instructions (especially for Greek text)
        3. Specify quality and edge handling requirements
        4. Include lighting and color consistency instructions
        5. Keep the enhanced prompt focused and actionable
        6. Use concrete technical language, no philosophical discussion

        OUTPUT: Enhanced prompt text ONLY. Start immediately with the prompt content."""

        # Build user message with optional image
        user_content = []

        # ✅ USE PNG BYTES FROM MEMORY (NO DOWNLOAD NEEDED)
        if original_image_bytes:
            logger.info(
                "🖼️ Converting PNG to base64 for enhancement",
                extra={"model": model_name, "size_kb": len(original_image_bytes) / 1024}
            )
            
            # Convert to base64 directly (PNG already in memory!)
            img_b64 = base64.b64encode(original_image_bytes).decode('utf-8')
            
            logger.info(
                "✅ PNG converted to base64 for enhancement",
                extra={"model": model_name}
            )
            
            # Add as base64 data URL
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_b64}",
                    "detail": "high"
                }
            })

        # Add text prompt
        user_content.append({
            "type": "text",
            "text": f"Original edit request: {original_prompt}\n\nOUTPUT ONLY THE ENHANCED PROMPT. NO EXPLANATIONS. NO QUESTIONS. JUST THE PROMPT TEXT:",
        })

        # Build messages with proper caching
        if cache_enabled:
            # Use content array with cache_control for caching
            payload = {
                "model": "anthropic/claude-sonnet-4.5",
                "messages": [
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "text",
                                "text": system_prompt,
                                "cache_control": {"type": "ephemeral"}
                            }
                        ]
                    },
                    {
                        "role": "user",
                        "content": user_content,
                    }
                ],
                "max_tokens": 2000,
                "temperature": 0.7,
            }
        else:
            # Standard payload without caching
            payload = {
                "model": "anthropic/claude-sonnet-4.5",
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_content,
                    }
                ],
                "max_tokens": 2000,
                "temperature": 0.7,
            }
        
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=None
            )

            print(f"🔍 API Response Status: {response.status_code}")
            print(f"🔍 API Response Headers: {dict(response.headers)}")
            print(f"🔍 Raw response length: {len(response.text)} chars")
            
            self._handle_response_errors(response)
            
            data = response.json()
            enhanced = data["choices"][0]["message"]["content"]
            
            logger.info(
                "Prompt enhanced successfully",
                extra={
                    "model": model_name,
                    "original_length": len(original_prompt),
                    "enhanced_length": len(enhanced),
                }
            )
            
            return enhanced.strip()
            
        except httpx.HTTPStatusError as e:
            self._handle_response_errors(e.response)
            raise  # Should not reach here
    
    @retry_async(max_attempts=3, exceptions=(httpx.RequestError, ProviderError))
    async def validate_image(
        self,
        image_url: str,
        original_image_bytes: bytes,  # ✅ Receive bytes not URL
        original_request: str,
        model_name: str,
        validation_prompt_template: str,
    ) -> ValidationResult:
        """
        Validate an edited image using Claude 4.5 Sonnet with vision.
        Downloads both images locally and sends as base64 for 100% reliability.
        
        Args:
            image_url: Temporary URL of generated image
            original_image_url: URL of original image
            original_request: Original edit request
            model_name: Model that generated the image
            validation_prompt_template: Validation prompt template
            
        Returns:
            ValidationResult
            
        Raises:
            ProviderError: If API request fails
        """
        self._ensure_client()
        
        try:
            # ✅ ORIGINAL PNG ALREADY IN MEMORY (NO DOWNLOAD!)
            logger.info(
                "✅ Using PNG from memory for validation",
                extra={"size_kb": len(original_image_bytes) / 1024}
            )
            
            # Only download the GENERATED image
            logger.info("📥 Downloading generated image for validation")
            async with httpx.AsyncClient(timeout=30.0) as download_client:
                generated_response = await download_client.get(image_url)
                generated_response.raise_for_status()
                generated_bytes = generated_response.content
            
            logger.info(
                "✅ Generated image downloaded",
                extra={"size_kb": len(generated_bytes) / 1024}
            )
            
            # Convert both images to base64
            original_b64 = base64.b64encode(original_image_bytes).decode('utf-8')  # ✅ Use bytes from memory
            generated_b64 = base64.b64encode(generated_bytes).decode('utf-8')
            
            logger.info("✅ Both images converted to base64, starting validation")
            
        except Exception as e:
            logger.error(
                f"Failed to download images for validation: {e}",
                extra={"error": str(e)}
            )
            raise ProviderError(
                "openrouter",
                f"Failed to download images for validation: {str(e)}",
                500
            )
        
        # Format validation prompt
        validation_prompt = validation_prompt_template.format(
            original_request=original_request,
            model_name=model_name,
        )
        
        # ✅ SEND AS BASE64 DATA URLS (100% reliable - no URL dependency)
        payload = {
            "model": "anthropic/claude-sonnet-4.5",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": validation_prompt,
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
                                "url": f"data:image/png;base64,{generated_b64}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1000,
            "temperature": 0.0,
        }
        
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            
            self._handle_response_errors(response)
            
            data = response.json()
            validation_text = data["choices"][0]["message"]["content"]

            print(f"\n{'='*80}")
            print(f"🔍 RAW VALIDATION RESPONSE for {model_name}")
            print(f"🔍 RAW VALIDATION RESPONSE for {model_name} (length: {len(validation_text)} chars)")
            print(f"{'='*80}")
            print(validation_text)
            print(f"{'='*80}\n")
            
            # Parse validation response
            result = self._parse_validation_response(validation_text, model_name)
            
            logger.info(
                "✅ Image validated successfully",
                extra={
                    "model": model_name,
                    "passed": result.passed,
                    "score": result.score,
                }
            )
            
            return result
            
        except httpx.HTTPStatusError as e:
            self._handle_response_errors(e.response)
            raise  # Should not reach here
    
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
            except:
                error_message = response.text
            
            raise ProviderError(
                "openrouter",
                error_message,
                response.status_code
            )