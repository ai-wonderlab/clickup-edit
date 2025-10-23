"""
Updated Orchestrator with Strict Dual Validation + Smart Retry System

Integrates:
1. StrictDualValidator (Claude + GPT-4)
2. SmartRetrySystem (incremental vs full restart)
3. Enhanced logging and metrics
"""
import time
from typing import Optional, List
from datetime import datetime

from .prompt_enhancer import PromptEnhancer
from .image_generator import ImageGenerator
from .strict_dual_validator import StrictDualValidator
from .smart_retry_system import SmartRetrySystem, RetryStrategy
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

logger = get_logger(__name__)


class OrchestratorWithSmartRetry:
    """
    Enhanced orchestrator with:
    - Strict dual AI validation (Claude + GPT-4)
    - Smart retry system (incremental vs restart)
    - Up to 5 retry attempts
    - Detailed logging and metrics
    """
    
    def __init__(
        self,
        enhancer: PromptEnhancer,
        generator: ImageGenerator,
        strict_dual_validator: StrictDualValidator,
        smart_retry_system: SmartRetrySystem,
        hybrid_fallback: HybridFallback,
        max_retries: int = 5
    ):
        """
        Initialize orchestrator with all components.
        
        Args:
            enhancer: PromptEnhancer instance
            generator: ImageGenerator instance
            strict_dual_validator: StrictDualValidator instance
            smart_retry_system: SmartRetrySystem instance
            hybrid_fallback: HybridFallback instance
            max_retries: Maximum retry attempts
        """
        self.enhancer = enhancer
        self.generator = generator
        self.validator = strict_dual_validator
        self.retry_system = smart_retry_system
        self.hybrid_fallback = hybrid_fallback
        self.max_retries = max_retries
        
        logger.info(
            "Orchestrator initialized with Smart Retry",
            extra={"max_retries": max_retries}
        )
    
    async def process_with_smart_retry(
        self,
        task_id: str,
        prompt: str,
        original_image_url: str,
        original_image_bytes: bytes
    ) -> ProcessResult:
        """
        Process edit request with intelligent retry system.
        
        Flow:
        1. Generate edited images (4 models in parallel)
        2. Validate with strict dual validation
        3. If fail: determine retry strategy
        4. Retry up to max_retries times
        5. If all fail: trigger hybrid fallback
        
        Args:
            task_id: ClickUp task ID
            prompt: User's edit request
            original_image_url: URL of original image
            original_image_bytes: PNG bytes of original image
            
        Returns:
            ProcessResult with final outcome
        """
        start_time = time.time()
        
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"🚀 STARTING TASK: {task_id}")
        logger.info("=" * 80)
        logger.info(f"📝 Request: {prompt}")
        logger.info(f"🎯 Max retries: {self.max_retries}")
        logger.info("")
        
        # State tracking
        retry_count = 0
        current_base_image_bytes = original_image_bytes
        current_base_image_url = original_image_url
        previous_issues: Optional[List[str]] = None
        edit_history = []
        all_validation_results = []
        
        # Main retry loop
        while retry_count <= self.max_retries:
            attempt_num = retry_count + 1
            iteration_start = time.time()
            
            logger.info("")
            logger.info("=" * 80)
            logger.info(f"📍 ATTEMPT {attempt_num}/{self.max_retries + 1}")
            logger.info("=" * 80)
            
            # Construct edit prompt (with retry instructions if needed)
            if retry_count == 0:
                # First attempt - use original request
                edit_prompt = prompt
                logger.info("🎨 First attempt - using original request")
            else:
                # Retry attempt - append retry instructions
                retry_info = edit_history[-1]['retry_strategy']
                edit_prompt = f"{prompt}\n\n{retry_info['retry_prompt']}"
                logger.info(
                    f"🔄 Retry attempt - strategy: {retry_info['strategy']}"
                )
                logger.info(f"📌 Base image: {retry_info['base_image']}")
            
            try:
                # ===================================================================
                # PHASE 1: ENHANCEMENT
                # ===================================================================
                logger.info("-" * 80)
                logger.info("PHASE 1: Prompt Enhancement")
                logger.info("-" * 80)
                
                include_image = (retry_count == 0)  # Only first attempt
                
                enhanced = await self.enhancer.enhance_all_parallel(
                    edit_prompt,
                    original_image_url=current_base_image_url,
                    original_image_bytes=current_base_image_bytes,
                    include_image=include_image
                )
                
                logger.info(
                    f"✅ Enhanced prompts: {len(enhanced)} models",
                    extra={"models": [e.model_name for e in enhanced]}
                )
                
                # ===================================================================
                # PHASE 2: GENERATION
                # ===================================================================
                logger.info("-" * 80)
                logger.info("PHASE 2: Image Generation")
                logger.info("-" * 80)
                
                generated = await self.generator.generate_all_parallel(
                    enhanced,
                    current_base_image_url
                )
                
                logger.info(
                    f"✅ Generated images: {len(generated)} successful",
                    extra={"models": [g.model_name for g in generated]}
                )
                
                # ===================================================================
                # PHASE 3: STRICT DUAL VALIDATION
                # ===================================================================
                logger.info("-" * 80)
                logger.info("PHASE 3: Strict Dual Validation")
                logger.info("-" * 80)
                
                # Validate all generated images
                validation_results = []
                
                for generated_image in generated:
                    logger.info(
                        f"🔍 Validating {generated_image.model_name}..."
                    )
                    
                    validation = await self.validator.validate(
                        original_image_bytes=original_image_bytes,  # Always compare to original
                        edited_image_bytes=generated_image.image_bytes,
                        original_request=prompt,
                        previous_issues=previous_issues  # Focus on past issues
                    )
                    
                    # Add model name to validation result
                    validation['model_name'] = generated_image.model_name
                    validation['generated_image'] = generated_image
                    
                    validation_results.append(validation)
                    
                    logger.info(
                        f"📊 {generated_image.model_name}: "
                        f"Decision={validation['decision']}, "
                        f"Score={validation['avg_score']:.1f}/10, "
                        f"Confidence={validation['confidence']}"
                    )
                
                all_validation_results.extend(validation_results)
                
                # ===================================================================
                # PHASE 4: SELECT BEST RESULT
                # ===================================================================
                logger.info("-" * 80)
                logger.info("PHASE 4: Result Selection")
                logger.info("-" * 80)
                
                # Find all passing results
                passing_results = [
                    v for v in validation_results
                    if v['decision'] == 'PASS' and v['avg_score'] >= 9.0
                ]
                
                if passing_results:
                    # Select highest scoring passing result
                    best = max(passing_results, key=lambda v: v['avg_score'])
                    
                    logger.info(
                        f"✅ Found passing result: {best['model_name']} "
                        f"(score: {best['avg_score']:.1f}/10)"
                    )
                    
                    processing_time = time.time() - start_time
                    
                    logger.info("")
                    logger.info("=" * 80)
                    logger.info(f"🎉 SUCCESS on attempt {attempt_num}!")
                    logger.info(f"🏆 Model: {best['model_name']}")
                    logger.info(f"📊 Score: {best['avg_score']:.1f}/10")
                    logger.info(f"⏱️  Time: {processing_time:.1f}s")
                    logger.info("=" * 80)
                    
                    return ProcessResult(
                        status=ProcessStatus.SUCCESS,
                        final_image=best['generated_image'],
                        iterations=attempt_num,
                        model_used=best['model_name'],
                        all_results=None,  # Not using old format
                        processing_time_seconds=processing_time
                    )
                
                # ===================================================================
                # PHASE 5: RETRY STRATEGY DECISION
                # ===================================================================
                logger.info("-" * 80)
                logger.info("PHASE 5: Retry Strategy Decision")
                logger.info("-" * 80)
                
                # Select best validation result (highest score) for retry decision
                best_validation = max(
                    validation_results,
                    key=lambda v: v['avg_score']
                )
                
                logger.info(
                    f"📊 Best attempt: {best_validation['model_name']} "
                    f"with score {best_validation['avg_score']:.1f}/10"
                )
                
                # Determine retry strategy
                retry_strategy = self.retry_system.determine_strategy(
                    validation_result=best_validation,
                    edit_request=prompt,
                    retry_count=retry_count,
                    original_image_b64=None,  # Not needed
                    edited_image_b64=None     # Not needed
                )
                
                logger.info(f"🧠 Strategy: {retry_strategy['strategy']}")
                logger.info(f"💭 Reason: {retry_strategy['reason']}")
                
                # Store attempt in history
                edit_history.append({
                    'attempt': attempt_num,
                    'best_score': best_validation['avg_score'],
                    'best_model': best_validation['model_name'],
                    'validation_result': best_validation,
                    'retry_strategy': retry_strategy,
                    'duration_seconds': time.time() - iteration_start
                })
                
                # ===================================================================
                # HANDLE RETRY STRATEGY
                # ===================================================================
                
                if retry_strategy['strategy'] == RetryStrategy.GIVE_UP:
                    # Max retries exceeded
                    logger.error("")
                    logger.error("=" * 80)
                    logger.error(f"❌ FAILED after {attempt_num} attempts")
                    logger.error(f"📊 Best score achieved: {best_validation['avg_score']:.1f}/10")
                    logger.error("=" * 80)
                    
                    # Trigger hybrid fallback
                    await self.hybrid_fallback.trigger_human_review(
                        task_id=task_id,
                        original_prompt=prompt,
                        iterations_attempted=attempt_num,
                        failed_results=[]  # Will need to adapt
                    )
                    
                    processing_time = time.time() - start_time
                    
                    return ProcessResult(
                        status=ProcessStatus.HYBRID_FALLBACK,
                        final_image=None,
                        iterations=attempt_num,
                        model_used=None,
                        all_results=None,
                        error=f"Failed after {attempt_num} attempts",
                        processing_time_seconds=processing_time
                    )
                
                elif retry_strategy['strategy'] == RetryStrategy.INCREMENTAL:
                    # Use best edited image for next attempt
                    logger.info("➡️  Next: Incremental fix using edited image")
                    
                    best_generated = best_validation['generated_image']
                    current_base_image_bytes = best_generated.image_bytes
                    current_base_image_url = best_generated.temp_url
                    previous_issues = retry_strategy.get('issues_to_focus', [])
                    retry_count += 1
                
                elif retry_strategy['strategy'] == RetryStrategy.FULL_RESTART:
                    # Use original image for next attempt
                    logger.info("➡️  Next: Full restart using original image")
                    
                    current_base_image_bytes = original_image_bytes
                    current_base_image_url = original_image_url
                    previous_issues = retry_strategy.get('issues_to_focus', [])
                    retry_count += 1
                
            except (AllEnhancementsFailed, AllGenerationsFailed) as e:
                logger.error(
                    f"❌ Critical failure in attempt {attempt_num}: {e}",
                    extra={"error": str(e)},
                    exc_info=True
                )
                
                # If last attempt, give up
                if retry_count >= self.max_retries:
                    break
                
                # Otherwise, retry from original
                logger.info("⚠️  Retrying from original image after failure")
                current_base_image_bytes = original_image_bytes
                current_base_image_url = original_image_url
                retry_count += 1
                continue
            
            except Exception as e:
                logger.error(
                    f"❌ Unexpected error in attempt {attempt_num}: {e}",
                    extra={"error": str(e)},
                    exc_info=True
                )
                
                # If last attempt, give up
                if retry_count >= self.max_retries:
                    break
                
                retry_count += 1
                continue
        
        # Should not reach here, but safety fallback
        processing_time = time.time() - start_time
        
        logger.error("❌ Unexpected exit from retry loop")
        
        return ProcessResult(
            status=ProcessStatus.FAILED,
            final_image=None,
            iterations=retry_count,
            model_used=None,
            all_results=None,
            error="Unexpected failure",
            processing_time_seconds=processing_time
        )