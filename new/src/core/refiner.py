"""Refinement component for iterative improvements based on validation feedback."""

import time
from typing import List, Optional

from .prompt_enhancer import PromptEnhancer
from .image_generator import ImageGenerator
from .validator import Validator
from ..models.schemas import ValidationResult, RefineResult, GeneratedImage
from ..utils.logger import get_logger

logger = get_logger(__name__)


class Refiner:
    """Refines prompts and regenerates images based on validation feedback."""
    
    def __init__(
        self,
        enhancer: PromptEnhancer,
        generator: ImageGenerator,
        validator: Validator,
    ):
        """
        Initialize refiner.
        
        Args:
            enhancer: PromptEnhancer instance
            generator: ImageGenerator instance
            validator: Validator instance
        """
        self.enhancer = enhancer
        self.generator = generator
        self.validator = validator
    
    def aggregate_feedback(
        self,
        failed_validations: List[ValidationResult],
    ) -> str:
        """
        Aggregate feedback from failed validations into actionable requirements.
        
        Args:
            failed_validations: List of validation results that failed
            
        Returns:
            Aggregated feedback string
        """
        all_issues = []
        
        for validation in failed_validations:
            if not validation.passed:
                all_issues.extend(validation.issues)
        
        # Deduplicate and format
        unique_issues = list(set(all_issues))
        
        # Remove "None" or empty issues
        unique_issues = [
            issue for issue in unique_issues
            if issue and issue.lower() not in ["none", "n/a"]
        ]
        
        if not unique_issues:
            return "Previous attempt had quality issues. Ensure all requirements are met."
        
        feedback = "IMPORTANT - Previous iteration failed with these issues:\n"
        for issue in unique_issues:
            feedback += f"- {issue}\n"
        feedback += "\nAddress ALL of these issues in the refinement."
        
        return feedback
    
    async def refine_with_feedback(
        self,
        original_prompt: str,
        original_image_url: str,
        failed_validations: List[ValidationResult],
    ) -> RefineResult:
        """
        Refine prompts based on validation feedback and regenerate.
        
        Args:
            original_prompt: Original user request
            original_image_url: URL of original image
            failed_validations: List of failed validation results
            
        Returns:
            RefineResult with new generations and validations
        """
        logger.info("Starting refinement iteration")
        
        # Aggregate feedback from failures
        feedback = self.aggregate_feedback(failed_validations)
        
        logger.info(
            "Feedback aggregated",
            extra={
                "issues_count": len(failed_validations),
                "feedback_length": len(feedback),
            }
        )
        
        # Create refined prompt with feedback incorporated
        refined_prompt = f"{original_prompt}\n\n{feedback}"
        
        logger.info(
            "Refined prompt created",
            extra={"refined_length": len(refined_prompt)}
        )
        
        # Re-run full pipeline with refined prompt
        enhanced = await self.enhancer.enhance_all_parallel(refined_prompt)
        
        generated = await self.generator.generate_all_parallel(
            enhanced,
            original_image_url
        )
        
        validated = await self.validator.validate_all_parallel(
            generated,
            refined_prompt
        )
        
        logger.info(
            "Refinement iteration complete",
            extra={
                "enhancements": len(enhanced),
                "generations": len(generated),
                "validations": len(validated),
                "passed": sum(1 for v in validated if v.passed),
            }
        )
        
        return RefineResult(
            enhanced=enhanced,
            generated=generated,
            validated=validated,
            refined_prompt=refined_prompt,
        )
    
    def parse_request_into_steps(self, request: str) -> List[str]:
        """
        Break complex request into individual sequential operations.
        
        Example:
        Input: "βαλε το λογοτυπο δεξια τελειως, αλλαξε το 20% σε 30% 
                και γραψε κατω απο το 'ΓΙΑ 48 ΩΡΕΣ' τη φραση 'ΕΚΤΟΣ ΑΠΟ FREDDO'
                Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
        
        Output:
        [
            "βαλε το λογοτυπο δεξια τελειως. Όλα τα υπολοιπα να μεινουνε ακριβως ιδια",
            "αλλαξε το 20% σε 30%. Όλα τα υπολοιπα να μεινουνε ακριβως ιδια",
            "γραψε κατω απο το 'ΓΙΑ 48 ΩΡΕΣ' τη φραση 'ΕΚΤΟΣ ΑΠΟ FREDDO'. Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
        ]
        """
        logger.info("🔗 Parsing request into sequential steps")
        
        # Remove preservation clause to parse operations
        preservation = ""
        if "Όλα τα υπολοιπα" in request:
            parts = request.split("Όλα τα υπολοιπα")
            request_part = parts[0].strip()
            preservation = "Όλα τα υπολοιπα" + parts[1]
        else:
            request_part = request.strip()
            preservation = "Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
        
        # Split by common delimiters
        # Handle both "," and " και " (Greek "and")
        request_normalized = request_part.replace(" και ", ",")
        
        # Split by comma
        operations = [op.strip() for op in request_normalized.split(",") if op.strip()]
        
        # Rebuild each operation with preservation clause
        steps = []
        for op in operations:
            step = f"{op}. {preservation}"
            steps.append(step)
        
        logger.info(
            f"📋 Parsed into {len(steps)} sequential steps",
            extra={"steps": steps}
        )
        
        return steps
    
    async def execute_sequential(
        self,
        steps: List[str],
        original_image_url: str,
        original_image_bytes: bytes,
        task_id: str
    ) -> Optional[GeneratedImage]:
        """
        Execute steps sequentially - each step:
        1. Uses ALL models in parallel (wan-2.5-edit, etc.)
        2. Gets full prompt enhancement with deep research
        3. Validates result
        4. Uses best passing result as input for next step
        
        Args:
            steps: List of individual operations to perform
            original_image_url: URL of original image
            original_image_bytes: Original image bytes
            task_id: ClickUp task ID for logging
            
        Returns:
            Final GeneratedImage if successful, None if any step fails
        """
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"🔗 SEQUENTIAL MODE: Executing {len(steps)} steps")
        logger.info("=" * 80)
        
        # Start with original image
        current_image_url = original_image_url
        current_image_bytes = original_image_bytes
        
        for i, step in enumerate(steps, 1):
            step_start = time.time()
            
            logger.info("")
            logger.info("-" * 80)
            logger.info(f"🔗 SEQUENTIAL STEP {i}/{len(steps)}")
            logger.info("-" * 80)
            logger.info(f"📝 Operation: {step}")
            logger.info(f"📌 Base image: {'original' if i == 1 else f'result from step {i-1}'}")
            
            try:
                # PHASE 1: Full enhancement with deep research (ALL models)
                logger.info(f"Phase 1: Enhancing step {i} for ALL models...")
                
                enhanced = await self.enhancer.enhance_all_parallel(
                    original_prompt=step,
                    original_image_url=current_image_url,
                    original_image_bytes=current_image_bytes,
                    include_image=True  # Include image for context
                )
                
                logger.info(
                    f"✅ Enhanced for {len(enhanced)} models",
                    extra={"models": [e.model_name for e in enhanced]}
                )
                
                # PHASE 2: Generate with ALL models in parallel
                logger.info(f"Phase 2: Generating with {len(enhanced)} models...")
                
                generated = await self.generator.generate_all_parallel(
                    enhanced,
                    current_image_url
                )
                
                logger.info(
                    f"✅ Generated {len(generated)} images",
                    extra={"models": [g.model_name for g in generated]}
                )
                
                # PHASE 3: Validate all results
                logger.info(f"Phase 3: Validating {len(generated)} results...")
                
                validated = await self.validator.validate_all_parallel(
                    generated,
                    step,
                    original_image_bytes  # Always compare to original
                )
                
                # Find best passing result
                passing = [v for v in validated if v.passed]
                
                if passing:
                    # Select highest scoring result
                    best_validation = max(passing, key=lambda v: v.score)
                    best_image = next(
                        img for img in generated
                        if img.model_name == best_validation.model_name
                    )
                    
                    step_duration = time.time() - step_start
                    
                    logger.info(
                        f"✅ STEP {i} PASSED",
                        extra={
                            "model": best_validation.model_name,
                            "score": best_validation.score,
                            "duration": f"{step_duration:.1f}s"
                        }
                    )
                    logger.info(
                        f"🏆 Best: {best_validation.model_name} "
                        f"with score {best_validation.score}/10"
                    )
                    
                    # Use this result as input for next step
                    current_image_url = best_image.temp_url
                    current_image_bytes = best_image.image_bytes
                    
                    # Store final result for last step
                    if i == len(steps):
                        logger.info("")
                        logger.info("=" * 80)
                        logger.info("🎉 ALL SEQUENTIAL STEPS COMPLETED SUCCESSFULLY!")
                        logger.info("=" * 80)
                        return best_image
                
                else:
                    # No passing results for this step
                    best_score = max((v.score for v in validated), default=0)
                    
                    logger.error(
                        f"❌ STEP {i} FAILED - No passing results",
                        extra={
                            "best_score": best_score,
                            "attempts": len(validated)
                        }
                    )
                    
                    # Log all failures
                    for v in validated:
                        logger.error(
                            f"  • {v.model_name}: {v.score}/10 - {v.issues}"
                        )
                    
                    logger.error("")
                    logger.error("=" * 80)
                    logger.error(f"💥 SEQUENTIAL MODE FAILED AT STEP {i}/{len(steps)}")
                    logger.error("=" * 80)
                    
                    return None
                
            except Exception as e:
                logger.error(
                    f"❌ Exception in sequential step {i}: {e}",
                    extra={"error": str(e)},
                    exc_info=True
                )
                return None
        
        # Should not reach here
        logger.error("Sequential execution completed but no final result")
        return None