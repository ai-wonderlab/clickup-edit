"""Prompt enhancement component with parallel processing."""

import asyncio
from typing import List, Dict, Optional

from ..providers.openrouter import OpenRouterClient
from ..models.schemas import EnhancedPrompt
from ..utils.logger import get_logger
from ..utils.errors import AllEnhancementsFailed
from ..utils.config import load_deep_research

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
        self.deep_research_cache: Dict[str, Dict[str, str]] = {}
    
    async def load_deep_research(self):
        """Load all deep research files into memory cache."""
        logger.info("Loading deep research files")
        
        for model_name in self.model_names:
            try:
                research = load_deep_research(model_name)
                
                # Combine activation and research into single prompt
                self.deep_research_cache[model_name] = (
                    research["activation"] + "\n\n" + research["research"]
                )
                
                logger.info(
                    f"Loaded deep research for {model_name}",
                    extra={
                        "model": model_name,
                        "total_length": len(self.deep_research_cache[model_name]),
                    }
                )
                
            except Exception as e:
                logger.error(
                    f"Failed to load deep research for {model_name}: {e}",
                    extra={"model": model_name, "error": str(e)}
                )
                # Continue loading other models
        
        logger.info(
            f"Deep research loaded for {len(self.deep_research_cache)} models",
            extra={"models": list(self.deep_research_cache.keys())}
        )
    
    async def enhance_single(
        self,
        original_prompt: str,
        model_name: str,
        original_image_url: str,
        original_image_bytes: Optional[bytes],  # ✅ Receive PNG
        include_image: bool = False,
    ) -> EnhancedPrompt:
        """
        Enhance prompt for a single model.
        
        Args:
            original_prompt: User's original edit request
            model_name: Target image model name
            
        Returns:
            EnhancedPrompt
            
        Raises:
            Exception: If enhancement fails
        """
        if model_name not in self.deep_research_cache:
            raise ValueError(f"Deep research not loaded for {model_name}")
        
        deep_research = self.deep_research_cache[model_name]
        
        logger.info(
            f"Enhancing prompt for {model_name}",
            extra={"model": model_name}
        )
        
        try:
            enhanced = await self.client.enhance_prompt(
                original_prompt=original_prompt,
                model_name=model_name,
                deep_research=deep_research,
                original_image_bytes=original_image_bytes if include_image else None,  # ✅ Pass bytes
                cache_enabled=True,
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
        original_image_url: Optional[str] = None,
        original_image_bytes: Optional[bytes] = None,  # ✅ Receive PNG
        include_image: bool = False,
    ) -> List[EnhancedPrompt]:
        """
        Enhance prompt for ALL models in parallel.
        
        Args:
            original_prompt: User's original edit request
            
        Returns:
            List of successful EnhancedPrompt objects
            
        Raises:
            AllEnhancementsFailed: If all enhancements fail
        """
        logger.info(
            f"Starting parallel enhancement for {len(self.model_names)} models",
            extra={"models": self.model_names}
        )
        
        # Create tasks for all models
        tasks = [
            self.enhance_single(original_prompt, model_name, original_image_url, 
                            original_image_bytes, include_image)
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