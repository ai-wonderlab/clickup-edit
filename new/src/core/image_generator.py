"""Image generation component with parallel processing."""

import asyncio
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
        original_image_url: str,
    ) -> GeneratedImage:
        """
        Generate image with a single model.
        
        Args:
            enhanced_prompt: Enhanced prompt for specific model
            original_image_url: URL of original image to edit
            
        Returns:
            GeneratedImage
            
        Raises:
            Exception: If generation fails
        """
        model_name = enhanced_prompt.model_name
        
        logger.info(
            f"Generating image with {model_name}",
            extra={"model": model_name}
        )
        
        try:
            # Generate image - returns tuple: (image_bytes, cloudfront_url)
            result = await self.client.generate_image(
                prompt=enhanced_prompt.enhanced,
                original_image_url=original_image_url,
                model_name=model_name,
            )

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
                f"Image generated with accessible URL",
                extra={
                    "model": model_name,
                    "url": temp_url[:100],
                    "bytes_size": len(image_bytes)
                }
            )

            return GeneratedImage(
                model_name=model_name,
                image_bytes=image_bytes,
                temp_url=temp_url,  # Real CloudFront URL
                original_image_url=original_image_url,
                prompt_used=enhanced_prompt.enhanced,
            )
            
        except Exception as e:
            logger.error(
                f"Generation failed for {model_name}",
                extra={"model": model_name, "error": str(e)}
            )
            raise
    
    async def generate_all_parallel(
        self,
        enhanced_prompts: List[EnhancedPrompt],
        original_image_url: str,
    ) -> List[GeneratedImage]:
        """
        Generate images with ALL enhanced prompts in parallel.
        
        Args:
            enhanced_prompts: List of enhanced prompts
            original_image_url: URL of original image
            
        Returns:
            List of successful GeneratedImage objects
            
        Raises:
            AllGenerationsFailed: If all generations fail
        """
        logger.info(
            f"Starting parallel generation for {len(enhanced_prompts)} models",
            extra={
                "models": [ep.model_name for ep in enhanced_prompts]
            }
        )
        
        # Create tasks for all prompts
        tasks = [
            self.generate_single(prompt, original_image_url)
            for prompt in enhanced_prompts
        ]
        
        # Execute in parallel with exception handling
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Separate successes from failures
        successful = []
        failed = []
        
        for i, result in enumerate(results):
            model_name = enhanced_prompts[i].model_name
            
            if isinstance(result, Exception):
                logger.error(
                    f"Generation failed for {model_name}",
                    extra={
                        "model": model_name,
                        "error": str(result),
                    }
                )
                failed.append((model_name, result))
            else:
                successful.append(result)
                logger.info(
                    f"Generation successful for {model_name}",
                    extra={
                        "model": model_name,
                        "image_size_kb": len(result.image_bytes) / 1024,
                        "temp_url": result.temp_url,
                    }
                )
        
        # Check if any succeeded
        if not successful:
            logger.error(
                f"All {len(enhanced_prompts)} generations failed",
                extra={"failures": len(failed)}
            )
            raise AllGenerationsFailed([e for _, e in failed])
        
        logger.info(
            f"Parallel generation complete: {len(successful)}/{len(enhanced_prompts)} successful",
            extra={
                "successful": len(successful),
                "failed": len(failed),
                "success_rate": f"{len(successful)/len(enhanced_prompts)*100:.1f}%",
            }
        )
        
        return successful