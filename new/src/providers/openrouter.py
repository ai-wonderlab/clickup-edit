"""OpenRouter API client for Claude and Gemini models."""

import json
import base64
import asyncio
import time
from typing import Dict, Any, Optional, List
import httpx

from .base import BaseProvider
from ..utils.logger import get_logger
from ..utils.errors import ProviderError, AuthenticationError, RateLimitError
from ..utils.retry import retry_async
from ..utils.images import resize_for_context
from ..utils.config import load_fonts_guide
from ..models.schemas import ValidationResult
from ..models.enums import ValidationStatus

logger = get_logger(__name__)


class OpenRouterClient(BaseProvider):
    """Client for OpenRouter API (Claude + Gemini)."""
    
    def __init__(self, api_key: str, timeout: float = None):
        """
        Initialize OpenRouter client.
        
        Args:
            api_key: OpenRouter API key
            timeout: Request timeout in seconds (defaults from config)
        """
        # ✅ NEW: Get config
        from ..utils.config import get_config
        config = get_config()
        
        # ✅ NEW: Use config timeout if not provided
        if timeout is None:
            timeout = config.timeout_openrouter_seconds
        
        super().__init__(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=timeout,
        )
        
        # ✅ NEW: Rate limiting from config
        self._enhancement_semaphore = asyncio.Semaphore(config.rate_limit_enhancement)
        self._validation_semaphore = asyncio.Semaphore(config.rate_limit_validation)
        
        logger.info(
            "OpenRouter rate limiting enabled",
            extra={
                "max_concurrent_enhancements": config.rate_limit_enhancement,
                "max_concurrent_validations": config.rate_limit_validation,
            }
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
        original_images_bytes: Optional[List[bytes]] = None,  # ✅ Multiple images
        cache_enabled: bool = True,
        previous_feedback: Optional[str] = None,  # ✅ Feedback from previous iteration
    ) -> str:
        """Enhance user prompt using Claude with system/user split."""
        self._ensure_client()
        
        logger.info("")
        logger.info("-" * 60)
        logger.info(f"🎨 ENHANCEMENT START - {model_name}")
        logger.info("-" * 60)
        
        # ============================================
        # INPUT LOGGING
        # ============================================
        logger.info(
            "📥 ENHANCEMENT INPUT",
            extra={
                "model": model_name,
                "original_prompt_length": len(original_prompt),
                "original_prompt": original_prompt,
                "deep_research_length": len(deep_research),
                "images_count": len(original_images_bytes) if original_images_bytes else 0,
                "cache_enabled": cache_enabled,
                "has_previous_feedback": previous_feedback is not None,
                "previous_feedback": previous_feedback[:200] if previous_feedback else None,
            }
        )
        
        # ✅ NEW: Acquire semaphore before API call
        async with self._enhancement_semaphore:
            logger.debug(
                f"Enhancement semaphore acquired for {model_name}",
                extra={
                    "model": model_name,
                    "semaphore_available": self._enhancement_semaphore._value,
                }
            )
            
            try:
                # ═══════════════════════════════════════════════════════════
                # SYSTEM PROMPT = Deep research + Fonts guide
                # ═══════════════════════════════════════════════════════════
                
                # Add fonts guide to system prompt
                fonts_guide = load_fonts_guide()
                fonts_section = ""
                if fonts_guide:
                    fonts_section = f"""

═══════════════════════════════════════════════════════════════
FONT TRANSLATION GUIDE
═══════════════════════════════════════════════════════════════
When the request mentions fonts, translate to appropriate equivalents:

{fonts_guide}

Use standard font names that image generation models understand.
═══════════════════════════════════════════════════════════════
"""
                    logger.info(
                        "📚 FONTS INJECTED INTO ENHANCEMENT",
                        extra={"fonts_length": len(fonts_guide)}
                    )
                
                system_prompt = deep_research + fonts_section + """

═══════════════════════════════════════════════════════════════
FINAL OUTPUT OVERRIDE:
═══════════════════════════════════════════════════════════════
Ignore any instructions above about warnings, recommendations, or alternatives.
Output ONLY the enhanced prompt. No meta-commentary. No markdown headers.
Just the pure editing instructions."""
                
                # ═══════════════════════════════════════════════════════════
                # USER PROMPT = Simple enhancement request + multi-image context
                # ═══════════════════════════════════════════════════════════
                
                # Add multi-image context if multiple images
                multi_image_context = ""
                if original_images_bytes and len(original_images_bytes) > 1:
                    multi_image_context = f"""
        [MULTI-IMAGE INPUT]
        You are viewing {len(original_images_bytes)} images.
        Each image's role and content is described in the request below.
        Use them according to their described purpose - do not assume which is "primary" or "secondary".

"""
                    logger.info(
                        "🖼️ MULTI-IMAGE CONTEXT ADDED",
                        extra={"image_count": len(original_images_bytes)}
                    )
                
                # Add feedback section if this is a retry iteration
                feedback_section = ""
                if previous_feedback:
                    feedback_section = f"""
═══════════════════════════════════════════════════════════════
⚠️ PREVIOUS ATTEMPT FEEDBACK (IMPORTANT - Address these issues):
═══════════════════════════════════════════════════════════════
{previous_feedback}

Your enhanced prompt MUST specifically address these issues.
Focus on fixing what went wrong in the previous attempt.
═══════════════════════════════════════════════════════════════

"""
                    logger.info(
                        "📝 FEEDBACK INJECTED INTO ENHANCEMENT PROMPT",
                        extra={"feedback_length": len(previous_feedback)}
                    )
                
                user_text = f"""{multi_image_context}{feedback_section}You are a TRANSLATOR, not a creative director.

Your job:
- Convert the user's request into precise technical instructions
- Include what the user asked for - don't invent requirements they didn't mention
- For unspecified details: follow the reference/inspiration if provided, otherwise use sensible defaults

Key understanding:
- CONTENT images (photos, products, models) are the canvas - their composition is final unless the user explicitly asks to change it
- INSPIRATION/REFERENCE images guide what you ADD: typography style, text placement, colors, overlay aesthetics
- Adapt overlay elements to fit the content image, not the other way around

What you must NEVER do (unless user explicitly requests it):
- Reposition, crop, or reframe the content photos
- Add creative ideas the user didn't ask for

                            Enhance this image editing request for {model_name}:

{original_prompt}

CRITICAL OUTPUT REQUIREMENTS:
- Return ONLY the enhanced prompt text ready for direct API submission
- NO explanations, warnings, recommendations, or meta-commentary
- NO "IMPORTANT", "CRITICAL", "RECOMMENDED", or markdown sections
- NO confidence levels, success predictions, or alternative approaches
- NO anti-pattern warnings or hybrid workflow suggestions
- Start immediately with the actual prompt instructions
- Output must be copy-paste ready for the image editing API

Your output MUST be the pure prompt with zero additional text."""
                
                # ═══════════════════════════════════════════════════════════
                # BUILD USER CONTENT (text + optional images)
                # ═══════════════════════════════════════════════════════════
                user_content = [
                    {
                        "type": "text",
                        "text": user_text
                    }
                ]
                
                # Add images if provided (resized for context efficiency)
                if original_images_bytes:
                    for i, img_bytes in enumerate(original_images_bytes):
                        resized = resize_for_context(img_bytes, max_dimension=512, quality=70)
                        img_b64 = base64.b64encode(resized).decode('utf-8')
                        user_content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_b64}"
                            }
                        })
                        logger.info(
                            f"🖼️ IMAGE {i+1} RESIZED FOR CONTEXT",
                            extra={
                                "image_index": i,
                                "original_size_kb": round(len(img_bytes) / 1024, 2),
                                "resized_size_kb": round(len(resized) / 1024, 2),
                            }
                        )
                
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
                
                logger.info(
                    "📝 ENHANCEMENT PROMPT TO CLAUDE",
                    extra={
                        "model": model_name,
                        "system_prompt_length": len(system_prompt),
                        "user_prompt_length": len(user_text),
                        "total_images": len(original_images_bytes) if original_images_bytes else 0,
                    }
                )
                
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
                        "effort": "high"  # High
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
                logger.info("🌐 CALLING CLAUDE API FOR ENHANCEMENT...")
                api_start = time.time()
                
                response = await self.client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    timeout=None
                )
                
                api_duration = time.time() - api_start
                
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
                
                # ═══════════════════════════════════════════════════════════
                # RETURN ENHANCED PROMPT
                # ═══════════════════════════════════════════════════════════
                enhanced = data["choices"][0]["message"]["content"]
                enhanced = enhanced.strip()
                
                # ============================================
                # RESULT LOGGING
                # ============================================
                logger.info("")
                logger.info(
                    f"✅ ENHANCEMENT COMPLETE - {model_name}",
                    extra={
                        "model": model_name,
                        "api_duration_seconds": round(api_duration, 2),
                        "original_length": len(original_prompt),
                        "enhanced_length": len(enhanced),
                    }
                )
                
                logger.info(
                    "📤 ENHANCED PROMPT",
                    extra={
                        "model": model_name,
                        "enhanced_prompt": enhanced,
                    }
                )
                
                return enhanced
                
            except Exception as e:
                logger.error(
                    f"Enhancement failed for {model_name}",
                    extra={
                        "model": model_name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True
                )
                
                # ✅ NEW: Raise exception - let orchestrator decide how to handle
                from ..utils.errors import EnhancementError
                raise EnhancementError(
                    f"Failed to enhance prompt for {model_name}: {str(e)}"
                )
            
            finally:
                logger.debug(
                    f"Enhancement semaphore released for {model_name}",
                    extra={"model": model_name}
                )
                # Semaphore auto-released by context manager
    
    @retry_async(max_attempts=3, exceptions=(httpx.RequestError, ProviderError))
    async def validate_image(
        self,
        image_url: str,  # Edited image (CloudFront URL)
        original_images_bytes: List[bytes],  # Original images (PNG bytes) - ALL of them
        original_request: str,  # User's request
        model_name: str,  # Which model generated it
        validation_prompt_template: str  # ✅ This becomes SYSTEM prompt
    ) -> ValidationResult:
        """Validate edited image using Claude with system/user split."""
        self._ensure_client()
        
        # ✅ NEW: Acquire semaphore before API call
        async with self._validation_semaphore:
            logger.debug(
                f"Validation semaphore acquired for {model_name}",
                extra={
                    "model": model_name,
                    "semaphore_available": self._validation_semaphore._value,
                }
            )
            
            try:
                # ═══════════════════════════════════════════════════════════
                # SYSTEM PROMPT = Entire validation prompt (290 lines)
                # ═══════════════════════════════════════════════════════════
                system_prompt = validation_prompt_template
                
                # ═══════════════════════════════════════════════════════════
                # USER PROMPT = Simple task with image count
                # ═══════════════════════════════════════════════════════════
                num_originals = len(original_images_bytes)
                if num_originals == 1:
                    user_text = f"""Validate this edit.

USER REQUEST: {original_request}

Compare IMAGE 1 (original) with IMAGE 2 (edited).
Return ONLY JSON."""
                else:
                    user_text = f"""Validate this edit.

USER REQUEST: {original_request}

Compare IMAGES 1-{num_originals} (originals/inputs) with FINAL IMAGE (edited result).
Verify ALL input images are properly incorporated in the output.
Return ONLY JSON."""
                
                # ═══════════════════════════════════════════════════════════
                # PREPARE IMAGES - ALL originals + edited
                # ═══════════════════════════════════════════════════════════
                # Build user content array
                user_content = [
                    {
                        "type": "text",
                        "text": user_text
                    }
                ]
                
                # ✅ FIX: Define max size limit for Claude
                MAX_SIZE_FOR_CLAUDE = 3.5 * 1024 * 1024  # 3.5MB raw → ~4.7MB base64 (under 5MB)
                
                # Add ALL original images - RESIZED FOR CLAUDE
                for i, original_bytes in enumerate(original_images_bytes):
                    # Resize if too large for Claude's 5MB limit
                    if len(original_bytes) > MAX_SIZE_FOR_CLAUDE:
                        logger.info(f"Original image {i+1} too large ({len(original_bytes)/1024/1024:.1f}MB), resizing")
                        original_bytes = resize_for_context(
                            original_bytes,
                            max_dimension=2048,
                            quality=85
                        )
                        # resize_for_context converts to JPEG
                        media_type = "image/jpeg"
                    else:
                        # Detect original format
                        from PIL import Image
                        import io
                        img = Image.open(io.BytesIO(original_bytes))
                        media_type = "image/jpeg" if img.format == "JPEG" else "image/png"
                    
                    original_b64 = base64.b64encode(original_bytes).decode('utf-8')
                    original_data_url = f"data:{media_type};base64,{original_b64}"
                    user_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": original_data_url
                        }
                    })
                    logger.info(f"📷 Added original image {i+1}/{num_originals} ({len(original_bytes)/1024:.1f}KB, {media_type})")
                
                logger.info("📥 Downloading edited image for validation")
                async with httpx.AsyncClient(timeout=30.0) as download_client:
                    edited_response = await download_client.get(image_url)
                    edited_response.raise_for_status()
                    edited_bytes = edited_response.content

                # ✅ Resize edited image if needed
                if len(edited_bytes) > MAX_SIZE_FOR_CLAUDE:
                    logger.warning(
                        f"Image too large for validation ({len(edited_bytes)/1024/1024:.1f}MB), resizing"
                    )
                    
                    # Use existing utility - converts to JPEG and resizes
                    edited_bytes = resize_for_context(
                        edited_bytes,
                        max_dimension=2048,  # Good enough for validation
                        quality=85           # Higher than default 70
                    )
                    
                    logger.info(f"Resized for validation: {len(edited_bytes)/1024:.1f}KB")
                    edited_b64 = base64.b64encode(edited_bytes).decode('utf-8')
                    edited_data_url = f"data:image/jpeg;base64,{edited_b64}"
                else:
                    # Small enough - use as-is but detect format
                    from PIL import Image
                    import io

                    edited_img = Image.open(io.BytesIO(edited_bytes))
                    image_format = edited_img.format  # JPEG, PNG, etc.
                    
                    if image_format == 'JPEG':
                        logger.info(f"✅ Keeping JPEG format for validation ({len(edited_bytes)/1024:.1f}KB)")
                        edited_b64 = base64.b64encode(edited_bytes).decode('utf-8')
                        edited_data_url = f"data:image/jpeg;base64,{edited_b64}"
                    else:
                        # Convert non-JPEG to JPEG for smaller size
                        logger.info(f"🔄 Converting {image_format} to JPEG format")
                        jpeg_buffer = io.BytesIO()
                        if edited_img.mode in ('RGBA', 'LA', 'P'):
                            edited_img = edited_img.convert('RGB')
                        edited_img.save(jpeg_buffer, format='JPEG', quality=90)
                        edited_jpeg_bytes = jpeg_buffer.getvalue()
                        edited_b64 = base64.b64encode(edited_jpeg_bytes).decode('utf-8')
                        edited_data_url = f"data:image/jpeg;base64,{edited_b64}"
                        logger.info(f"✅ Converted: {len(edited_bytes)/1024:.1f}KB → {len(edited_jpeg_bytes)/1024:.1f}KB JPEG")
                
                # Add edited image as LAST image
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": edited_data_url
                    }
                })
                
                logger.info(f"✅ All {num_originals + 1} images prepared for validation (originals + edited)")
                
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
                        "content": user_content  # ✅ All images in order
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

                    "reasoning": {
                        "effort": "high"
                    },
                    
                    # ✅ LOCK PROVIDER (prevent fallbacks)
                    "provider": {
                        "order": ["Anthropic"],
                        "allow_fallbacks": False
                    }
                }
                
                # ═══════════════════════════════════════════════════════════
                # DEBUG LOGGING
                # ═══════════════════════════════════════════════════════════
                total_original_size_kb = sum(len(b) for b in original_images_bytes) / 1024
                logger.error(
                    f"🔍 DEBUG VALIDATION REQUEST for {model_name}",
                    extra={
                        "model": payload["model"],
                        "num_original_images": num_originals,
                        "total_original_size_kb": round(total_original_size_kb, 2),
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
            
            finally:
                logger.debug(
                    f"Validation semaphore released for {model_name}",
                    extra={"model": model_name}
                )
                # Semaphore auto-released by context manager
    
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
            from ..utils.config import get_config
            config = get_config()
            expected_pass = "PASS" if score >= config.validation_pass_threshold else "FAIL"
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