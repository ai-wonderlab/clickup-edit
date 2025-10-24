"""Main orchestrator coordinating the entire edit workflow."""

import time
from typing import Optional, List
from datetime import datetime

from .prompt_enhancer import PromptEnhancer
from .image_generator import ImageGenerator
from .validator import Validator
from .refiner import Refiner
from .hybrid_fallback import HybridFallback
from ..models.schemas import (
    ProcessResult,
    ValidationResult,
    GeneratedImage,
    IterationMetrics,
)
from ..models.enums import ProcessStatus
from ..utils.logger import get_logger
from ..utils.errors import AllEnhancementsFailed, AllGenerationsFailed
from ..utils.config import Config

logger = get_logger(__name__)


class Orchestrator:
    """Orchestrates the complete image editing workflow."""
    
    def __init__(
        self,
        enhancer: PromptEnhancer,
        generator: ImageGenerator,
        validator: Validator,
        refiner: Refiner,
        hybrid_fallback: HybridFallback,
        max_iterations: int = 3,
        config: Config = None,
    ):
        """
        Initialize orchestrator.
        
        Args:
            enhancer: PromptEnhancer instance
            generator: ImageGenerator instance
            validator: Validator instance
            refiner: Refiner instance
            hybrid_fallback: HybridFallback instance
            max_iterations: Maximum refinement iterations
        """
        self.enhancer = enhancer
        self.generator = generator
        self.validator = validator
        self.refiner = refiner
        self.hybrid_fallback = hybrid_fallback
        self.max_iterations = max_iterations

        if config:
            self.MAX_STEP_ATTEMPTS = config.max_step_attempts
            self.PASS_THRESHOLD = config.validation_pass_threshold
        else:
            self.MAX_STEP_ATTEMPTS = 2
            self.PASS_THRESHOLD = 8
    
    def select_best_result(
        self,
        validations: List[ValidationResult],
        generated_images: List[GeneratedImage],
    ) -> Optional[GeneratedImage]:
        """
        Select best validated result or None if all failed.
        
        Args:
            validations: List of validation results
            generated_images: List of generated images
            
        Returns:
            Best GeneratedImage or None
        """
        # Find all that passed validation
        passed = [v for v in validations if v.passed]
        
        # 🔍 DEBUG
        logger.info(
            f"🔍 DEBUG select_best_result details",
            extra={
                "total_validations": len(validations),
                "passed_count": len(passed),
                "all_validations": [
                    {
                        "model": v.model_name,
                        "passed": v.passed,
                        "passed_type": type(v.passed),
                        "score": v.score,
                    }
                    for v in validations
                ],
            }
        )

        if not passed:
            logger.info("No results passed validation")
            return None
        
        # Select highest scoring result
        best = max(passed, key=lambda v: v.score)
        
        logger.info(
            f"Best result selected: {best.model_name} with score {best.score}",
            extra={
                "model": best.model_name,
                "score": best.score,
                "passed_count": len(passed),
            }
        )
        
        # Find corresponding image
        best_image = next(
            img for img in generated_images
            if img.model_name == best.model_name
        )
        
        return best_image
    
    async def process_with_iterations(
        self,
        task_id: str,
        prompt: str,
        original_image_url: str,
        original_image_bytes: bytes,  # ✅ Receive PNG bytes
    ) -> ProcessResult:
        """
        Process edit request with iterative refinement.
        
        Args:
            task_id: ClickUp task ID
            prompt: User's edit request
            original_image_url: URL of original image
            
        Returns:
            ProcessResult with final outcome
        """
        start_time = time.time()
        
        logger.info(
            "Starting edit processing",
            extra={
                "task_id": task_id,
                "max_iterations": self.max_iterations,
            }
        )
        
        current_prompt = prompt
        all_iterations: List[IterationMetrics] = []
        all_validation_results: List[ValidationResult] = []
        
        for iteration in range(1, self.max_iterations + 1):
            iteration_start = time.time()
            
            logger.info(
                f"Iteration {iteration}/{self.max_iterations}",
                extra={
                    "task_id": task_id,
                    "iteration": iteration,
                }
            )
            
            try:
                # Phase 1: Parallel Enhancement
                logger.info("Phase 1: Enhancement", extra={"iteration": iteration})
                include_image = (iteration == 1)

                # 🎯 ENHANCEMENT PHASE
                enhanced = await self.enhancer.enhance_all_parallel(
                    current_prompt,
                    original_image_url=original_image_url,
                    original_image_bytes=original_image_bytes,  # ✅ Pass bytes
                    include_image=include_image
                )
                
                if include_image:
                    logger.info(
                        "🖼️ Sent original image to Claude for context-aware enhancement",
                        extra={"iteration": iteration}
                    )
                
                # Phase 2: Parallel Generation
                logger.info("Phase 2: Generation", extra={"iteration": iteration})
                generated = await self.generator.generate_all_parallel(
                    enhanced,
                    original_image_url
                )
                
                # Phase 3: Parallel Validation
                logger.info("Phase 3: Validation", extra={"iteration": iteration})
                validated = await self.validator.validate_all_parallel(
                    generated,
                    current_prompt,
                    original_image_bytes  # ✅ Pass bytes
                )
                
                all_validation_results.extend(validated)
                
                # Record iteration metrics
                iteration_metrics = IterationMetrics(
                    iteration_number=iteration,
                    enhancements_successful=len(enhanced),
                    generations_successful=len(generated),
                    validations_passed=sum(1 for v in validated if v.passed),
                    best_score=max((v.score for v in validated if v.passed), default=0),
                    duration_seconds=time.time() - iteration_start,
                )
                all_iterations.append(iteration_metrics)
                
                logger.info(
                    f"Iteration {iteration} complete",
                    extra={
                        "task_id": task_id,
                        "iteration": iteration,
                        "enhancements": len(enhanced),
                        "generations": len(generated),
                        "validations_passed": iteration_metrics.validations_passed,
                        "best_score": iteration_metrics.best_score,
                        "duration_seconds": iteration_metrics.duration_seconds,
                    }
                )
                
                # Phase 4: Decision Logic
                best_result = self.select_best_result(validated, generated)

                # 🔍 DEBUG LOGGING
                logger.info(
                    f"🔍 DEBUG select_best_result",
                    extra={
                        "best_result_exists": best_result is not None,
                        "validated_count": len(validated),
                        "validated_details": [
                            {
                                "model": v.model_name,
                                "passed": v.passed,
                                "score": v.score,
                            }
                            for v in validated
                        ],
                    }
                )
                
                if best_result:
                    # SUCCESS!
                    processing_time = time.time() - start_time
                    
                    logger.info(
                        "Processing successful",
                        extra={
                            "task_id": task_id,
                            "iterations": iteration,
                            "model_used": best_result.model_name,
                            "processing_time_seconds": processing_time,
                        }
                    )
                    
                    return ProcessResult(
                        status=ProcessStatus.SUCCESS,
                        final_image=best_result,
                        iterations=iteration,
                        model_used=best_result.model_name,
                        all_results=all_validation_results,
                        processing_time_seconds=processing_time,
                    )
                
                # ========================================================
                # NEW: Check if we should switch to SEQUENTIAL mode
                # ========================================================
                if iteration >= 3:
                    # Failed 3 times - try sequential breakdown
                    logger.warning(
                        f"Failed {iteration} iterations - switching to SEQUENTIAL mode",
                        extra={"task_id": task_id}
                    )
                    
                    # Parse request into steps
                    steps = self.refiner.parse_request_into_steps(prompt)
                    
                    if len(steps) > 1:
                        logger.info(
                            f"🔗 Breaking request into {len(steps)} sequential operations",
                            extra={"steps": steps}
                        )
                        
                        # Execute sequentially
                        final_image = await self.refiner.execute_sequential(
                            steps=steps,
                            original_image_url=original_image_url,
                            original_image_bytes=original_image_bytes,
                            task_id=task_id,
                            max_step_attempts=self.MAX_STEP_ATTEMPTS,
                        )
                        
                        if final_image:
                            processing_time = time.time() - start_time
                            
                            return ProcessResult(
                                status=ProcessStatus.SUCCESS,
                                final_image=final_image,
                                iterations=iteration,
                                model_used=f"{final_image.model_name} (sequential)",
                                all_results=all_validation_results,
                                processing_time_seconds=processing_time,
                            )
                        else:
                            logger.error("Sequential mode also failed")
                            # Continue to hybrid fallback
                            break
                    else:
                        logger.info("Request is single operation - cannot break down further")
                
                # No passing results - refine if iterations remaining
                if iteration < self.max_iterations:
                    logger.info(
                        f"No passing results, refining for iteration {iteration + 1}",
                        extra={
                            "task_id": task_id,
                            "iteration": iteration,
                        }
                    )
                    
                    # Phase 5: Refinement
                    refinement = await self.refiner.refine_with_feedback(
                        prompt,
                        original_image_url,
                        validated,
                    )

                    # ✅ CHECK IF REFINEMENT PRODUCED A PASSING RESULT
                    if refinement.validated:
                        best_refined = self.select_best_result(
                            refinement.validated,
                            refinement.generated
                        )
                        
                        if best_refined:
                            processing_time = time.time() - start_time
                            
                            logger.info(
                                "✅ REFINEMENT SUCCESSFUL - Returning immediately",
                                extra={
                                    "task_id": task_id,
                                    "iteration": iteration,
                                    "model_used": best_refined.model_name,
                                    "score": refinement.validated[0].score,
                                    "processing_time_seconds": processing_time,
                                }
                            )
                            
                            return ProcessResult(
                                status=ProcessStatus.SUCCESS,
                                final_image=best_refined,
                                iterations=iteration,
                                model_used=best_refined.model_name,
                                all_results=all_validation_results + refinement.validated,
                                processing_time_seconds=processing_time,
                            )
                    
                    # Update prompt with feedback for next iteration
                    current_prompt = refinement.refined_prompt
                    
                    logger.info(
                        "Refinement complete, continuing to next iteration",
                        extra={
                            "task_id": task_id,
                            "iteration": iteration,
                            "refined_prompt_length": len(current_prompt),
                        }
                    )
                
            except (AllEnhancementsFailed, AllGenerationsFailed) as e:
                logger.error(
                    f"Critical failure in iteration {iteration}",
                    extra={
                        "task_id": task_id,
                        "iteration": iteration,
                        "error": str(e),
                    }
                )
                
                # Record failed iteration
                iteration_metrics = IterationMetrics(
                    iteration_number=iteration,
                    enhancements_successful=0,
                    generations_successful=0,
                    validations_passed=0,
                    best_score=0,
                    duration_seconds=time.time() - iteration_start,
                    errors=[str(e)],
                )
                all_iterations.append(iteration_metrics)
                
                # If this was the last iteration, fall through to hybrid fallback
                if iteration == self.max_iterations:
                    break
                    
                # Otherwise, continue to next iteration
                continue
            
            except Exception as e:
                logger.error(
                    f"Unexpected error in iteration {iteration}",
                    extra={
                        "task_id": task_id,
                        "iteration": iteration,
                        "error": str(e),
                    }
                )
                
                # Record error and continue if iterations remain
                iteration_metrics = IterationMetrics(
                    iteration_number=iteration,
                    enhancements_successful=0,
                    generations_successful=0,
                    validations_passed=0,
                    best_score=0,
                    duration_seconds=time.time() - iteration_start,
                    errors=[str(e)],
                )
                all_iterations.append(iteration_metrics)
                
                if iteration == self.max_iterations:
                    break
                continue
        
        # All iterations exhausted - trigger hybrid fallback
        processing_time = time.time() - start_time
        
        logger.warning(
            "All iterations failed, triggering hybrid fallback",
            extra={
                "task_id": task_id,
                "iterations": self.max_iterations,
                "processing_time_seconds": processing_time,
            }
        )
        
        await self.hybrid_fallback.trigger_human_review(
            task_id=task_id,
            original_prompt=prompt,
            iterations_attempted=self.max_iterations,
            failed_results=all_validation_results,
        )
        
        return ProcessResult(
            status=ProcessStatus.HYBRID_FALLBACK,
            final_image=None,
            iterations=self.max_iterations,
            model_used=None,
            all_results=all_validation_results,
            error=f"Failed after {self.max_iterations} iterations",
            processing_time_seconds=processing_time,
        )