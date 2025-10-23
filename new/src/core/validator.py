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
        Validate ALL generated images in parallel.
        
        Args:
            generated_images: List of generated images
            original_request: Original user edit request
            
        Returns:
            List of ValidationResult objects (includes failures as ERROR status)
        """
        logger.info(
            f"Starting parallel validation for {len(generated_images)} images",
            extra={
                "models": [img.model_name for img in generated_images]
            }
        )
        
        # Create tasks for all images
        tasks = [
            self.validate_single(image, original_request, original_image_bytes)
            for image in generated_images
        ]
        
        # Execute in parallel with exception handling
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Separate successes from failures
        validation_results = []
        successful = 0
        failed = 0
        
        for i, result in enumerate(results):
            model_name = generated_images[i].model_name
            
            if isinstance(result, Exception):
                print(f"\n🔴 VALIDATION EXCEPTION for {model_name}: {type(result).__name__}: {str(result)}")
                logger.error(
                    f"Validation error for {model_name}: {type(result).__name__}: {str(result)}",
                    extra={
                        "model": model_name,
                        "error": str(result),
                        "error_type": type(result).__name__,
                    }
                )
                # Create failed validation result
                validation_results.append(
                    ValidationResult(
                        model_name=model_name,
                        passed=False,
                        score=0,
                        issues=[f"Validation error: {str(result)}"],
                        reasoning="Validation process failed",
                        status="error",
                    )
                )
                failed += 1
            else:
                validation_results.append(result)
                if result.passed:
                    successful += 1
                else:
                    failed += 1
        
        logger.info(
            f"Parallel validation complete: {successful} passed, {failed} failed/errored",
            extra={
                "total": len(generated_images),
                "passed": successful,
                "failed": failed,
                "pass_rate": f"{successful/len(generated_images)*100:.1f}%",
            }
        )
        
        return validation_results