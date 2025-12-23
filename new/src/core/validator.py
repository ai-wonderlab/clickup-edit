"""Validation component with parallel validation using Gemini."""

import asyncio
import base64
import time
from typing import List

from ..providers.openrouter import OpenRouterClient
from ..models.schemas import GeneratedImage, ValidationResult
from ..utils.logger import get_logger
from ..utils.config import load_validation_prompt, load_fonts_guide
from ..utils.images import resize_for_context

logger = get_logger(__name__)


class Validator:
    """Validates generated images using Gemini 2.5 Pro with vision."""
    
    def __init__(self, openrouter_client: OpenRouterClient):
        """
        Initialize validator.
        
        Args:
            openrouter_client: OpenRouter API client
        """
        self.client = openrouter_client
        self.validation_prompt_template = None  # Default (SIMPLE_EDIT)
        self.validation_prompt_branded = None   # BRANDED_CREATIVE
        self._fonts_guide = None
    
    def load_validation_prompt(self):
        """Load validation prompt templates from file and inject fonts guide."""
        logger.info("Loading validation prompt templates")
        
        # Load fonts guide once
        self._fonts_guide = load_fonts_guide()
        
        # Load default (SIMPLE_EDIT) prompt
        self.validation_prompt_template = load_validation_prompt("SIMPLE_EDIT")
        if self._fonts_guide and "{fonts_guide}" in self.validation_prompt_template:
            self.validation_prompt_template = self.validation_prompt_template.replace(
                "{fonts_guide}", self._fonts_guide
            )
        logger.info(
            "Default validation prompt loaded",
            extra={"length": len(self.validation_prompt_template)}
        )
        
        # Load BRANDED_CREATIVE prompt
        self.validation_prompt_branded = load_validation_prompt("BRANDED_CREATIVE")
        if self._fonts_guide and "{fonts_guide}" in self.validation_prompt_branded:
            self.validation_prompt_branded = self.validation_prompt_branded.replace(
                "{fonts_guide}", self._fonts_guide
            )
        logger.info(
            "Branded validation prompt loaded",
            extra={"length": len(self.validation_prompt_branded)}
        )
    
    async def validate_single(
        self,
        generated_image: GeneratedImage,
        original_request: str,
        original_images_bytes: List[bytes],  # ✅ Multiple original images
        task_type: str = "SIMPLE_EDIT",  # ✅ NEW: Task type for validation criteria
    ) -> ValidationResult:
        """
        Validate a single generated image.
        
        Args:
            generated_image: Generated image to validate
            original_request: Original user edit request
            original_images_bytes: List of original image bytes for comparison
            task_type: Task type for validation criteria
            
        Returns:
            ValidationResult
            
        Raises:
            Exception: If validation fails
        """
        if not self.validation_prompt_template:
            raise RuntimeError("Validation prompt not loaded. Call load_validation_prompt() first.")
        
        model_name = generated_image.model_name
        
        logger.info("")
        logger.info("-" * 60)
        logger.info(f"✅ VALIDATION START - {model_name}")
        logger.info("-" * 60)
        
        # ============================================
        # INPUT LOGGING
        # ============================================
        logger.info(
            "📥 VALIDATION INPUT",
            extra={
                "model": model_name,
                "task_type": task_type,
                "original_image_count": len(original_images_bytes),
                "original_sizes_kb": [round(len(b) / 1024, 2) for b in original_images_bytes],
                "edited_size_kb": round(len(generated_image.image_bytes) / 1024, 2),
                "request_length": len(original_request),
                "request_full": original_request,
            }
        )
        
        # Select prompt based on task type
        if task_type == "BRANDED_CREATIVE":
            base_prompt = self.validation_prompt_branded or self.validation_prompt_template
            prompt_source = "branded"
        else:
            base_prompt = self.validation_prompt_template
            prompt_source = "default"
        
        formatted_prompt = base_prompt
        
        logger.info(
            "📝 VALIDATION PROMPT SELECTED",
            extra={
                "task_type": task_type,
                "prompt_source": prompt_source,
                "prompt_length": len(formatted_prompt),
            }
        )
        
        validation_start = time.time()
        
        try:
            # Pass ALL original images for comprehensive validation
            result = await self.client.validate_image(
                image_url=generated_image.temp_url,
                original_images_bytes=original_images_bytes,  # ✅ Pass ALL images
                original_request=original_request,
                model_name=model_name,
                validation_prompt_template=formatted_prompt,
            )

            validation_duration = time.time() - validation_start

            # ============================================
            # RESULT LOGGING
            # ============================================
            logger.info("")
            logger.info("-" * 40)
            logger.info(f"✅ VALIDATION RESULT - {model_name}")
            logger.info("-" * 40)
            
            logger.info(
                "📊 VALIDATION SCORE",
                extra={
                    "model": result.model_name,
                    "passed": result.passed,
                    "score": result.score,
                    "threshold": 8,
                    "issues": result.issues,
                    "reasoning": result.reasoning,
                    "validation_time_seconds": round(validation_duration, 2),
                }
            )
            
            if result.passed:
                logger.info(f"✅ PASSED with score {result.score}/10")
            else:
                logger.warning(f"❌ FAILED with score {result.score}/10")
                logger.warning(f"   Issues: {result.issues}")
            
            return result
            
        except Exception as e:
            validation_duration = time.time() - validation_start
            logger.error(
                f"❌ VALIDATION FAILED - {model_name}",
                extra={
                    "model": model_name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_seconds": round(validation_duration, 2),
                }
            )
            import traceback
            traceback.print_exc()
            raise
    
    async def validate_all_parallel(
        self,
        generated_images: List[GeneratedImage],
        original_request: str,
        original_images_bytes: List[bytes],  # ✅ Multiple original images
        task_type: str = "SIMPLE_EDIT",  # ✅ NEW: Task type for validation criteria
    ) -> List[ValidationResult]:
        """
        Validate ALL generated images SEQUENTIALLY with delays.
        
        ✅ IMPORTANT: This method no longer catches exceptions.
        System errors (network, rate limit, etc.) will bubble up to orchestrator.
        Only validation quality issues are returned as ValidationResult.
        
        Args:
            generated_images: List of generated images
            original_request: Original user edit request
            original_images_bytes: List of original image bytes
            task_type: Task type for validation criteria
            
        Returns:
            List of ValidationResult objects (only quality assessments)
            
        Raises:
            Exception: Any system error (network, API, parsing, etc.)
        """
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ SEQUENTIAL VALIDATION START")
        logger.info("=" * 60)
        
        logger.info(
            "📥 VALIDATION BATCH INPUT",
            extra={
                "image_count": len(generated_images),
                "models": [img.model_name for img in generated_images],
                "num_original_images": len(original_images_bytes),
                "task_type": task_type,
            }
        )
        
        validation_start = time.time()
        
        # ✅ NEW: No try/except - let exceptions bubble
        validation_results = []
        
        for i, image in enumerate(generated_images):
            logger.info(
                f"🔄 Validating image {i+1}/{len(generated_images)}: {image.model_name}"
            )
            
            # Call validation - any exception bubbles up immediately
            result = await self.validate_single(
                image,
                original_request,
                original_images_bytes,  # ✅ Pass all original images
                task_type,
            )
            
            validation_results.append(result)
            
            # Add delay between validations (except after last one)
            if i < len(generated_images) - 1:
                # ✅ NEW: Use config value
                from ..utils.config import get_config
                config = get_config()
                delay = config.validation_delay_seconds
                
                logger.info(
                    f"⏱️ Waiting {delay} seconds before next validation (avoid rate limits)"
                )
                await asyncio.sleep(delay)
        
        validation_duration = time.time() - validation_start
        
        # Calculate success statistics
        successful = sum(1 for r in validation_results if r.passed)
        failed = len(validation_results) - successful
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ SEQUENTIAL VALIDATION COMPLETE")
        logger.info("=" * 60)
        
        logger.info(
            "📊 VALIDATION SUMMARY",
            extra={
                "total_time_seconds": round(validation_duration, 2),
                "total": len(generated_images),
                "passed": successful,
                "failed": failed,
                "pass_rate": f"{successful/len(generated_images)*100:.1f}%",
                "results": [
                    {
                        "model": r.model_name,
                        "passed": r.passed,
                        "score": r.score,
                        "issues_count": len(r.issues),
                    }
                    for r in validation_results
                ],
            }
        )
        
        return validation_results