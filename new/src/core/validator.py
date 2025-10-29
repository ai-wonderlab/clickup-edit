"""Validation component with parallel validation using Gemini."""

import asyncio
from typing import List

from ..providers.openrouter import OpenRouterClient
from ..models.schemas import GeneratedImage, ValidationResult
from ..utils.logger import get_logger
from ..utils.config import load_validation_prompt

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
        self.validation_prompt_template = None
    
    def load_validation_prompt(self):
        """Load validation prompt template from file."""
        logger.info("Loading validation prompt template")
        self.validation_prompt_template = load_validation_prompt()
        logger.info(
            "Validation prompt loaded",
            extra={"length": len(self.validation_prompt_template)}
        )
    
    async def validate_single(
        self,
        generated_image: GeneratedImage,
        original_request: str,
        original_image_bytes: bytes,  # ✅ Receive PNG
    ) -> ValidationResult:
        """
        Validate a single generated image.
        
        Args:
            generated_image: Generated image to validate
            original_request: Original user edit request
            
        Returns:
            ValidationResult
            
        Raises:
            Exception: If validation fails
        """
        if not self.validation_prompt_template:
            raise RuntimeError("Validation prompt not loaded. Call load_validation_prompt() first.")
        
        model_name = generated_image.model_name
        
        logger.info(
            f"Validating image from {model_name}",
            extra={"model": model_name}
        )
        
        try:
            result = await self.client.validate_image(
                image_url=generated_image.temp_url,
                original_image_bytes=original_image_bytes,  # ✅ Pass bytes not URL
                original_request=original_request,
                model_name=model_name,
                validation_prompt_template=self.validation_prompt_template,
            )

            print(f"\n{'='*80}")
            print(f"🎯 VALIDATION RESULT for {model_name}")
            print(f"📊 Score: {result.score}/10")
            print(f"✅ Passed: {result.passed}")
            print(f"🚨 Issues: {result.issues}")
            print(f"💭 Reasoning: {result.reasoning[:200]}...")
            print(f"{'='*80}\n")
            
            logger.info(
                f"Validation complete for {model_name}",
                extra={
                    "model": model_name,
                    "passed": result.passed,
                    "score": result.score,
                    "issues": len(result.issues),
                }
            )
            
            return result
            
        except Exception as e:
            logger.error(
                f"Validation failed for {model_name}: {type(e).__name__}: {str(e)}",
                extra={"model": model_name, "error": str(e), "error_type": type(e).__name__}
            )
            print(f"\n🔴 VALIDATION EXCEPTION: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
    
    async def validate_all_parallel(
        self,
        generated_images: List[GeneratedImage],
        original_request: str,
        original_image_bytes: bytes,  # ✅ Receive PNG
    ) -> List[ValidationResult]:
        """
        Validate ALL generated images SEQUENTIALLY with delays.
        
        ✅ IMPORTANT: This method no longer catches exceptions.
        System errors (network, rate limit, etc.) will bubble up to orchestrator.
        Only validation quality issues are returned as ValidationResult.
        
        Args:
            generated_images: List of generated images
            original_request: Original user edit request
            original_image_bytes: Original image bytes
            
        Returns:
            List of ValidationResult objects (only quality assessments)
            
        Raises:
            Exception: Any system error (network, API, parsing, etc.)
        """
        logger.info(
            f"Starting sequential validation for {len(generated_images)} images",
            extra={
                "models": [img.model_name for img in generated_images]
            }
        )
        
        # ✅ NEW: No try/except - let exceptions bubble
        validation_results = []
        
        for i, image in enumerate(generated_images):
            logger.info(
                f"Validating image {i+1}/{len(generated_images)}: {image.model_name}"
            )
            
            # Call validation - any exception bubbles up immediately
            result = await self.validate_single(
                image,
                original_request,
                original_image_bytes
            )
            
            validation_results.append(result)
            
            logger.info(
                f"Validation complete for {image.model_name}",
                extra={
                    "model": image.model_name,
                    "passed": result.passed,
                    "score": result.score,
                }
            )
            
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
        
        # Calculate success statistics
        successful = sum(1 for r in validation_results if r.passed)
        failed = len(validation_results) - successful
        
        logger.info(
            f"Sequential validation complete: {successful} passed, {failed} failed",
            extra={
                "total": len(generated_images),
                "passed": successful,
                "failed": failed,
                "pass_rate": f"{successful/len(generated_images)*100:.1f}%",
            }
        )
        
        return validation_results