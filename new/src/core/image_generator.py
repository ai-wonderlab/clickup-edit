"""Image generation component with parallel processing."""

import asyncio
import time
from typing import List

from ..providers.wavespeed import WaveSpeedAIClient
from ..models.schemas import EnhancedPrompt, GeneratedImage
from ..utils.logger import get_logger
from ..utils.errors import AllGenerationsFailed

logger = get_logger(__name__)


class ImageGenerator:
    """Generates edited images using multiple models in parallel."""
    
    def __init__(self, wavespeed_client: WaveSpeedAIClient):
        """
        Initialize image generator.
        
        Args:
            wavespeed_client: WaveSpeedAI API client
        """
        self.client = wavespeed_client
    
    async def generate_single(
        self,
        enhanced_prompt: EnhancedPrompt,
        image_urls: List[str],  # ← CHANGED: Now accepts list of URLs
        aspect_ratio: str = None,  # ← NEW: Aspect ratio for output
    ) -> GeneratedImage:
        """
        Generate image with a single model.
        
        Args:
            enhanced_prompt: Enhanced prompt for specific model
            image_urls: List of image URLs to edit (supports multi-image)
            aspect_ratio: Optional aspect ratio for the output image
            
        Returns:
            GeneratedImage
            
        Raises:
            Exception: If generation fails
        """
        model_name = enhanced_prompt.model_name
        
        logger.info("")
        logger.info("-" * 60)
        logger.info(f"🖼️ GENERATION START - {model_name}")
        logger.info("-" * 60)
        
        logger.info(
            "📥 GENERATION INPUT",
            extra={
                "model": model_name,
                "prompt_length": len(enhanced_prompt.enhanced),
                "prompt_preview": enhanced_prompt.enhanced[:200] + "..." if len(enhanced_prompt.enhanced) > 200 else enhanced_prompt.enhanced,
                "image_url_count": len(image_urls),
                "image_urls": [url[:80] + "..." if len(url) > 80 else url for url in image_urls],
            }
        )
        
        gen_start = time.time()
        
        try:
            # Generate image - returns tuple: (image_bytes, cloudfront_url)
            result = await self.client.generate_image(
                prompt=enhanced_prompt.enhanced,
                image_urls=image_urls,  # ← CHANGED: Pass list of URLs
                model_name=model_name,
                aspect_ratio=aspect_ratio,  # ← NEW: Pass aspect ratio
            )

            gen_duration = time.time() - gen_start

            # Unpack result
            if isinstance(result, tuple):
                image_bytes, temp_url = result
            else:
                # Fallback for old format
                image_bytes = result
                import base64
                b64 = base64.b64encode(image_bytes).decode('utf-8')
                temp_url = f"data:image/jpeg;base64,{b64}"

            logger.info(
                f"✅ GENERATION COMPLETE - {model_name}",
                extra={
                    "model": model_name,
                    "generation_time_seconds": round(gen_duration, 2),
                    "result_size_kb": round(len(image_bytes) / 1024, 2),
                    "temp_url": temp_url[:100] if temp_url else None,
                }
            )

            return GeneratedImage(
                model_name=model_name,
                image_bytes=image_bytes,
                temp_url=temp_url,  # Real CloudFront URL
                original_image_url=image_urls[0],  # ← Primary image URL for reference
                prompt_used=enhanced_prompt.enhanced,
            )
            
        except Exception as e:
            gen_duration = time.time() - gen_start
            logger.error(
                f"❌ GENERATION FAILED - {model_name}",
                extra={
                    "model": model_name,
                    "error": str(e),
                    "duration_seconds": round(gen_duration, 2),
                }
            )
            raise
    
    async def generate_all_parallel(
        self,
        enhanced_prompts: List[EnhancedPrompt],
        image_urls: List[str],  # ← CHANGED: Now accepts list of URLs
        aspect_ratio: str = None,  # ← NEW: Aspect ratio for output
    ) -> List[GeneratedImage]:
        """
        Generate images with ALL enhanced prompts in parallel.
        
        Args:
            enhanced_prompts: List of enhanced prompts
            image_urls: List of image URLs to edit (supports multi-image)
            aspect_ratio: Optional aspect ratio for the output image
            
        Returns:
            List of successful GeneratedImage objects
            
        Raises:
            AllGenerationsFailed: If all generations fail
        """
        logger.info("")
        logger.info("=" * 60)
        logger.info("🖼️ PARALLEL GENERATION START")
        logger.info("=" * 60)
        
        logger.info(
            "📥 PARALLEL GENERATION INPUT",
            extra={
                "model_count": len(enhanced_prompts),
                "models": [ep.model_name for ep in enhanced_prompts],
                "image_url_count": len(image_urls),
                "prompts": [
                    {
                        "model": ep.model_name,
                        "length": len(ep.enhanced),
                        "preview": ep.enhanced[:100],
                    }
                    for ep in enhanced_prompts
                ],
            }
        )
        
        gen_start = time.time()
        
        # Create tasks for all prompts
        tasks = [
            self.generate_single(prompt, image_urls, aspect_ratio)  # ← CHANGED: Pass list of URLs + aspect_ratio
            for prompt in enhanced_prompts
        ]
        
        # Execute in parallel with exception handling
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        gen_duration = time.time() - gen_start
        
        # Separate successes from failures
        successful = []
        failed = []
        
        for i, result in enumerate(results):
            model_name = enhanced_prompts[i].model_name
            
            if isinstance(result, Exception):
                logger.error(
                    f"❌ Generation failed for {model_name}",
                    extra={
                        "model": model_name,
                        "error": str(result),
                    }
                )
                failed.append((model_name, result))
            else:
                successful.append(result)
        
        # Check if any succeeded
        if not successful:
            logger.error(
                f"❌ All {len(enhanced_prompts)} generations failed",
                extra={"failures": len(failed)}
            )
            raise AllGenerationsFailed([e for _, e in failed])
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("🖼️ PARALLEL GENERATION COMPLETE")
        logger.info("=" * 60)
        
        logger.info(
            "📊 GENERATION SUMMARY",
            extra={
                "total_time_seconds": round(gen_duration, 2),
                "models_attempted": len(enhanced_prompts),
                "successful": len(successful),
                "failed": len(failed),
                "success_rate": f"{len(successful)/len(enhanced_prompts)*100:.1f}%",
                "results": [
                    {
                        "model": r.model_name,
                        "size_kb": round(len(r.image_bytes) / 1024, 2),
                        "temp_url": r.temp_url[:80] if r.temp_url else None,
                    }
                    for r in successful
                ],
                "failures": [
                    {
                        "model": name,
                        "error": str(err)[:100],
                    }
                    for name, err in failed
                ],
            }
        )
        
        return successful