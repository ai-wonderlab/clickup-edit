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
from ..utils.config_manager import config_manager
from ..utils.task_logger import task_logger

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
            # Fallback to ConfigManager (or hardcoded defaults)
            self.MAX_STEP_ATTEMPTS = config_manager.get_parameter("MAX_STEP_ATTEMPTS", default=2)
            self.PASS_THRESHOLD = config_manager.get_parameter("VALIDATION_PASS_THRESHOLD", default=8)
    
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
        original_image_bytes: bytes,
        task_type: str = "SIMPLE_EDIT",
        additional_image_urls: List[str] = None,      # → WaveSpeed generation
        additional_image_bytes: List[bytes] = None,   # → WaveSpeed generation
        context_image_bytes: List[bytes] = None,      # ✅ NEW: → Claude enhancement only
        aspect_ratio: str = None,                     # ✅ NEW: Aspect ratio for WaveSpeed
        run_id: str = None,                           # ✅ Unique ID for this pipeline run
    ) -> ProcessResult:
        """
        Process edit request with iterative refinement.
        
        Args:
            task_id: ClickUp task ID
            prompt: User's edit request
            original_image_url: URL of original image
            original_image_bytes: Original image bytes
            task_type: Task type for validation (SIMPLE_EDIT or BRANDED_CREATIVE)
            additional_image_urls: Extra images for WaveSpeed generation
            additional_image_bytes: Extra image bytes for WaveSpeed generation
            context_image_bytes: ALL images for Claude enhancement context (includes reference/inspiration)
            aspect_ratio: Aspect ratio for WaveSpeed output (e.g., "16:9", "1:1")
            run_id: Unique identifier for this pipeline run (for log separation)
            
        Returns:
            ProcessResult with final outcome
        """
        start_time = time.time()
        
        logger.info(
            "Starting edit processing",
            extra={
                "task_id": task_id,
                "max_iterations": self.max_iterations,
                "has_context_images": context_image_bytes is not None,
                "context_count": len(context_image_bytes) if context_image_bytes else 0,
            }
        )
        
        # Log start of task processing
        task_logger.log_phase(
            task_id=task_id,
            phase="start",
            run_id=run_id,
            input_data={
                "prompt": prompt[:500] if prompt else None,
                "image_count": len(context_image_bytes) if context_image_bytes else 1,
                "task_type": task_type,
                "aspect_ratio": aspect_ratio,
            }
        )
        
        # Build image lists for GENERATION (WaveSpeed)
        generation_urls = [original_image_url]
        if additional_image_urls:
            generation_urls.extend(additional_image_urls)
        
        generation_bytes = [original_image_bytes]
        if additional_image_bytes:
            generation_bytes.extend(additional_image_bytes)
        
        # Build image list for ENHANCEMENT (Claude) - includes ALL context
        # If context_image_bytes provided, use that (includes inspiration/sketch)
        # Otherwise fall back to generation_bytes
        enhancement_bytes = context_image_bytes if context_image_bytes else generation_bytes
        
        current_prompt = prompt
        all_iterations: List[IterationMetrics] = []
        all_validation_results: List[ValidationResult] = []
        previous_validation_feedback: Optional[str] = None  # Track feedback for enhancement retries
        
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
                # Phase 1: Parallel Enhancement - uses ALL images (including reference)
                logger.info("Phase 1: Enhancement", extra={"iteration": iteration})
                
                # Always include images - Claude needs context on every iteration
                enhanced = await self.enhancer.enhance_all_parallel(
                    current_prompt,
                    original_images_bytes=enhancement_bytes,  # Always send images for context
                    previous_feedback=previous_validation_feedback,  # Pass feedback from previous iteration
                )
                
                logger.info(
                    "🖼️ Sent ALL images to Claude for context-aware enhancement",
                    extra={
                        "iteration": iteration,
                        "num_images": len(enhancement_bytes) if enhancement_bytes else 0,
                        "includes_reference": context_image_bytes is not None,
                        "has_previous_feedback": previous_validation_feedback is not None,
                    }
                )
                
                # Log enhancement phase with FULL LLM OUTPUT
                task_logger.log_phase(
                    task_id=task_id,
                    phase="enhancement",
                    run_id=run_id,
                    iteration=iteration,
                    model_used="claude-sonnet-4.5",
                    input_data={
                        "original_prompt": current_prompt,
                        "has_previous_feedback": previous_validation_feedback is not None,
                        "image_count": len(enhancement_bytes) if enhancement_bytes else 0,
                    },
                    output_data={
                        "enhanced_count": len(enhanced),
                        "llm_responses": [
                            {
                                "model": ep.model_name,
                                "enhanced_prompt": ep.enhanced,
                            }
                            for ep in enhanced
                        ]
                    },
                    success=len(enhanced) > 0
                )
                
                # Phase 2: Parallel Generation - uses ONLY include images (no reference)
                logger.info("Phase 2: Generation", extra={"iteration": iteration})
                
                generated = await self.generator.generate_all_parallel(
                    enhanced,
                    generation_urls,  # ✅ Only images to include in output
                    aspect_ratio,     # ✅ NEW: Pass aspect ratio to WaveSpeed
                )
                
                # Log generation phase with model details
                task_logger.log_phase(
                    task_id=task_id,
                    phase="generation",
                    run_id=run_id,
                    iteration=iteration,
                    model_used=generated[0].model_name if generated else None,
                    output_data={
                        "generated_count": len(generated),
                        "models_used": [g.model_name for g in generated],
                        "aspect_ratio": aspect_ratio,
                    },
                    success=len(generated) > 0
                )
                
                # Phase 3: Parallel Validation
                logger.info("Phase 3: Validation", extra={"iteration": iteration})
                
                try:
                    validated = await self.validator.validate_all_parallel(
                        generated,
                        current_prompt,
                        generation_bytes,  # ✅ Only input images (no reference)
                        task_type,  # ✅ Pass task type for validation criteria
                    )
                    
                    all_validation_results.extend(validated)
                    
                    # Log validation phase with FULL LLM OUTPUT
                    best_score = max((v.score for v in validated), default=0)
                    task_logger.log_phase(
                        task_id=task_id,
                        phase="validation",
                        run_id=run_id,
                        iteration=iteration,
                        model_used="claude-sonnet-4.5",
                        output_data={
                            "best_score": best_score,
                            "passed_count": sum(1 for v in validated if v.passed),
                            "validation_results": [
                                {
                                    "model": v.model_name,
                                    "score": v.score,
                                    "passed": v.passed,
                                    "issues": v.issues,
                                    "reasoning": v.reasoning,
                                }
                                for v in validated
                            ]
                        },
                        success=any(v.passed for v in validated)
                    )
                    
                    # Capture feedback for next iteration's enhancement
                    failed_validations = [v for v in validated if not v.passed]
                    if failed_validations:
                        # Get the best failed result's issues for feedback
                        best_failed = max(failed_validations, key=lambda v: v.score)
                        previous_validation_feedback = (
                            f"Previous attempt failed (score {best_failed.score}/10). "
                            f"Issues: {', '.join(best_failed.issues)}"
                        )
                        logger.info(
                            "📝 Captured validation feedback for next iteration",
                            extra={
                                "iteration": iteration,
                                "feedback": previous_validation_feedback,
                            }
                        )
                    
                except Exception as validation_error:
                    # ✅ NEW: Distinguish validation system errors from quality failures
                    logger.error(
                        f"Validation system error in iteration {iteration}",
                        extra={
                            "task_id": task_id,
                            "iteration": iteration,
                            "error": str(validation_error),
                            "error_type": type(validation_error).__name__,
                        },
                        exc_info=True
                    )
                    
                    # If this was the last iteration, fail
                    if iteration == self.max_iterations:
                        logger.error(
                            f"Validation failed in final iteration, triggering hybrid fallback",
                            extra={"task_id": task_id}
                        )
                        break
                    
                    # Otherwise, retry next iteration
                    logger.warning(
                        f"Validation failed, retrying iteration {iteration + 1}",
                        extra={"task_id": task_id, "iteration": iteration}
                    )
                    continue
                
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
                    
                    # Log final success result
                    best_validation = next(
                        (v for v in validated if v.model_name == best_result.model_name),
                        None
                    )
                    task_logger.log_result(
                        task_id=task_id,
                        clickup_task_id=task_id,
                        request=prompt[:500] if prompt else "",
                        score=best_validation.score if best_validation else 0,
                        passed=True,
                        model_used=best_result.model_name,
                        iterations=iteration,
                        run_id=run_id
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
                        original_image_bytes,  # ✅ ADD bytes for validation
                        validated,
                        aspect_ratio,          # ✅ NEW: Pass aspect ratio
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
        
        # Log fallback phase
        task_logger.log_phase(
            task_id=task_id,
            phase="fallback",
            run_id=run_id,
            output_data={"reason": "max_iterations_exceeded"},
            success=False
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