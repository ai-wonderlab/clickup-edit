"""Prompt enhancement component with parallel processing."""

import asyncio
from typing import List, Dict, Optional

from ..providers.openrouter import OpenRouterClient
from ..models.schemas import EnhancedPrompt
from ..utils.logger import get_logger
from ..utils.errors import AllEnhancementsFailed
from ..utils.config_manager import config_manager

logger = get_logger(__name__)


class PromptEnhancer:
    """Enhances user prompts for image editing models."""
    
    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        model_names: List[str],
    ):
        """
        Initialize prompt enhancer.
        
        Args:
            openrouter_client: OpenRouter API client
            model_names: List of image model names to enhance for
        """
        self.client = openrouter_client
        self.model_names = model_names
        # NOTE: Deep research is loaded FRESH for each enhancement to pick up Supabase changes
    
    async def load_deep_research(self):
        """Legacy method - now a no-op. Deep research is loaded fresh per-enhancement."""
        logger.info("load_deep_research() called - deep research now loaded fresh per-task")
    
    def _get_deep_research_fresh(self, model_name: str) -> str:
        """
        Load deep research FRESH from Supabase for each task.
        This ensures prompt changes in UI take effect immediately without redeploy.
        
        Args:
            model_name: The model to get research for
            
        Returns:
            Combined activation + research string, or empty string if not found
        """
        logger.info(f"🔄 Loading deep research fresh for model: {model_name}")
        
        try:
            research = config_manager.get_deep_research(model_name)
            
            if not research["activation"] and not research["research"]:
                logger.warning(f"No deep research found for {model_name}")
                return ""
            
            combined = research["activation"] + "\n\n" + research["research"]
            logger.info(f"Deep research loaded fresh for {model_name}: {len(combined)} chars")
            return combined
            
        except Exception as e:
            logger.error(f"Failed to load deep research for {model_name}: {e}")
            return ""
    
    async def enhance_single(
        self,
        original_prompt: str,
        model_name: str,
        original_images_bytes: Optional[List[bytes]] = None,  # ✅ Multiple images
        previous_feedback: Optional[str] = None,  # ✅ Feedback from previous iteration
    ) -> EnhancedPrompt:
        """
        Enhance prompt for a single model.
        
        Args:
            original_prompt: User's original edit request
            model_name: Target image model name
            original_images_bytes: Optional list of image bytes for context
            previous_feedback: Feedback from previous iteration's validation
            
        Returns:
            EnhancedPrompt
            
        Raises:
            Exception: If enhancement fails
        """
        # ═══════════════════════════════════════════════════════════════
        # LOAD DEEP RESEARCH FRESH FROM SUPABASE (not cached!)
        # This ensures prompt changes in UI take effect immediately without redeploy
        # ═══════════════════════════════════════════════════════════════
        deep_research = self._get_deep_research_fresh(model_name)
        
        if not deep_research:
            logger.warning(f"No deep research available for {model_name}, proceeding without it")
        
        logger.info(
            f"Enhancing prompt for {model_name}",
            extra={
                "model": model_name, 
                "num_images": len(original_images_bytes) if original_images_bytes else 0,
                "deep_research_loaded_fresh": True
            }
        )
        
        try:
            enhanced = await self.client.enhance_prompt(
                original_prompt=original_prompt,
                model_name=model_name,
                deep_research=deep_research,
                original_images_bytes=original_images_bytes,  # ✅ Pass all images
                cache_enabled=True,
                previous_feedback=previous_feedback,  # ✅ Pass feedback for retry context
            )

            logger.info(
                f"🎨 ENHANCED PROMPT for {model_name}",
                extra={
                    "model": model_name,
                    "original_prompt": original_prompt[:200],
                    "enhanced_prompt": enhanced[:500],
                    "deep_research_used": len(deep_research),
                }
            )

            # Also log as plain text for readability
            print(f"\n{'='*80}")
            print(f"🎨 MODEL: {model_name}")
            print(f"{'='*80}")
            print(f"📝 ORIGINAL: {original_prompt}")
            print(f"\n✨ ENHANCED:\n{enhanced}\n")
            print(f"{'='*80}\n")
            
            return EnhancedPrompt(
                model_name=model_name,
                original=original_prompt,
                enhanced=enhanced,
            )
            
        except Exception as e:
            logger.error(
                f"Enhancement failed for {model_name}",
                extra={"model": model_name, "error": str(e)}
            )
            raise
    
    async def enhance_all_parallel(
        self,
        original_prompt: str,
        original_images_bytes: Optional[List[bytes]] = None,  # ✅ Multiple images
        previous_feedback: Optional[str] = None,  # ✅ Feedback from previous iteration
    ) -> List[EnhancedPrompt]:
        """
        Enhance prompt for ALL models in parallel.
        
        Args:
            original_prompt: User's original edit request
            original_images_bytes: Optional list of image bytes for context
            previous_feedback: Feedback from previous iteration's validation
            
        Returns:
            List of successful EnhancedPrompt objects
            
        Raises:
            AllEnhancementsFailed: If all enhancements fail
        """
        logger.info(
            f"Starting parallel enhancement for {len(self.model_names)} models",
            extra={"models": self.model_names, "num_images": len(original_images_bytes) if original_images_bytes else 0}
        )
        
        # Create tasks for all models
        tasks = [
            self.enhance_single(
                original_prompt,
                model_name,
                original_images_bytes,
                previous_feedback,  # ✅ Pass feedback to each model's enhancement
            )
            for model_name in self.model_names
        ]
        
        # Execute in parallel with exception handling
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Separate successes from failures
        successful = []
        failed = []
        
        for i, result in enumerate(results):
            model_name = self.model_names[i]
            
            if isinstance(result, Exception):
                logger.error(
                    f"Enhancement failed for {model_name}",
                    extra={
                        "model": model_name,
                        "error": str(result),
                    }
                )
                failed.append((model_name, result))
            else:
                successful.append(result)
                logger.info(
                    f"Enhancement successful for {model_name}",
                    extra={
                        "model": model_name,
                        "enhanced_length": len(result.enhanced),
                    }
                )
        
        # Check if any succeeded
        if not successful:
            logger.error(
                f"All {len(self.model_names)} enhancements failed",
                extra={"failures": len(failed)}
            )
            raise AllEnhancementsFailed([e for _, e in failed])
        
        logger.info(
            f"Parallel enhancement complete: {len(successful)}/{len(self.model_names)} successful",
            extra={
                "successful": len(successful),
                "failed": len(failed),
                "success_rate": f"{len(successful)/len(self.model_names)*100:.1f}%",
            }
        )
        
        return successful