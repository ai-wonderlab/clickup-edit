"""Refinement component for iterative improvements based on validation feedback."""

from typing import List

from .prompt_enhancer import PromptEnhancer
from .image_generator import ImageGenerator
from .validator import Validator
from ..models.schemas import ValidationResult, RefineResult
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