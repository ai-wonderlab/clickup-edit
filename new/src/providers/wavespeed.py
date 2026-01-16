"""WaveSpeedAI API client - CORRECT implementation."""

import httpx
import asyncio
import time
from typing import Optional, Dict, Any, List

from .base import BaseProvider
from ..utils.logger import get_logger
from ..utils.errors import ProviderError, AuthenticationError, RateLimitError
from ..utils.retry import retry_async

logger = get_logger(__name__)


class WaveSpeedAIClient(BaseProvider):
    """Client for WaveSpeedAI image editing API."""
    
    def __init__(self, api_key: str, timeout: Optional[float] = None):
        # Use config value if not explicitly provided
        if timeout is None:
            from ..utils.config import get_config
            config = get_config()
            timeout = config.timeout_wavespeed_seconds
        
        super().__init__(
            api_key=api_key,
            base_url="https://api.wavespeed.ai/api/v3",
            timeout=timeout,
        )
    
    def _get_default_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
    
    @retry_async(max_attempts=3, exceptions=(httpx.RequestError, ProviderError))
    async def generate_image(
        self,
        prompt: str,
        image_urls: List[str],  # ← CHANGED: Now accepts list of URLs
        model_name: str,
        aspect_ratio: str = None,  # ← NEW: Aspect ratio for output (e.g., "16:9", "1:1")
    ) -> tuple[bytes, str]:
        """Generate edited image using WaveSpeed API.
        
        Args:
            prompt: The edit prompt
            image_urls: List of image URLs to use (supports multi-image)
            model_name: The model to use
            aspect_ratio: Optional aspect ratio for the output image
        
        Returns:
            Tuple of (image_bytes, cloudfront_url)
        """
        self._ensure_client()
        
        logger.info("")
        logger.info("-" * 60)
        logger.info(f"🚀 WAVESPEED API START - {model_name}")
        logger.info("-" * 60)
        
        # CORRECT model mapping with REAL endpoints
        model_mapping = {
            "seedream-v4": "bytedance/seedream-v4/edit",
            "qwen-edit-plus": "wavespeed-ai/qwen-image/edit-plus",
            "wan-2.5-edit": "alibaba/wan-2.5/image-edit",
            "nano-banana": "google/nano-banana/edit",
            # ✅ NEW: Nano Banana Pro models
            "nano-banana-pro-edit": "google/nano-banana-pro/edit",
            "nano-banana-pro-edit-ultra": "google/nano-banana-pro/edit-ultra",
        }
        
        model_id = model_mapping.get(model_name, model_name)
        
        # CORRECT payload structure - uses "images" array!
        payload = {
            "images": image_urls,  # ← CHANGED: Use the list directly
            "prompt": prompt,
            "enable_base64_output": False,
            "enable_sync_mode": False,
        }
        
        # Add aspect_ratio if provided
        if aspect_ratio:
            payload["aspect_ratio"] = aspect_ratio
            logger.info(f"📐 Aspect ratio set: {aspect_ratio}")
        
        # Add model-specific parameters
        if "qwen" in model_name.lower():
            payload["seed"] = -1
            payload["output_format"] = "jpeg"
        elif model_name == "nano-banana-pro-edit-ultra":
            # ✅ nano-banana-pro ULTRA specific settings (4K resolution)
            payload["output_format"] = "png"
            payload["resolution"] = "4k"
        elif model_name == "nano-banana-pro-edit":
            # ✅ nano-banana-pro specific settings (1K resolution)
            payload["output_format"] = "png"
            payload["resolution"] = "1k"
        elif "nano-banana" in model_name.lower():
            payload["output_format"] = "jpeg"
        elif "wan" in model_name.lower():
            payload["seed"] = -1
        
        logger.info(
            "� WAVESPEED INPUT",
            extra={
                "model": model_name,
                "model_id": model_id,
                "prompt_length": len(prompt),
                "prompt_preview": prompt[:200] + "..." if len(prompt) > 200 else prompt,
                "image_count": len(image_urls),
                "image_urls": [u[:80] + "..." if len(u) > 80 else u for u in image_urls],
            }
        )
        
        logger.info(
            "📦 WAVESPEED PAYLOAD",
            extra={"payload_keys": list(payload.keys()), "prompt_len": len(payload.get('prompt', ''))}
        )
        
        gen_start = time.time()
        
        try:
            # STEP 1: Submit task
            response = await self.client.post(
                f"{self.base_url}/{model_id}",
                json=payload,
            )
            
            if response.status_code != 200:
                logger.error(
                    f"❌ WaveSpeed submit failed: {response.status_code} - {response.text}",
                    extra={
                        "status": response.status_code,
                        "response": response.text,
                    }
                )
                raise ProviderError(
                    "wavespeed",
                    f"Submit failed: {response.text}",
                    response.status_code
                )
            
            result = response.json()
            
            if result.get("code") != 200:
                logger.error(
                    f"❌ WaveSpeed API error: {result}",
                    extra={"response": result}
                )
                raise ProviderError(
                    "wavespeed",
                    f"API error: {result.get('message', 'Unknown error')}"
                )
            
            task_data = result.get("data", {})
            task_id = task_data.get("id")
            
            if not task_id:
                logger.error("❌ No task ID in response", extra={"response": result})
                raise ProviderError("wavespeed", "No task ID in response")
            
            logger.info(
                "✅ TASK SUBMITTED",
                extra={
                    "model": model_name,
                    "task_id": task_id,
                    "status": task_data.get("status"),
                }
            )
            
            # STEP 2: Poll for completion
            image_url, execution_time = await self._poll_for_result(task_id, model_name)

            # STEP 3: Download image
            image_bytes = await self._download_image(image_url)
            
            gen_duration = time.time() - gen_start

            logger.info(
                f"✅ WAVESPEED COMPLETE - {model_name}",
                extra={
                    "model": model_name,
                    "task_id": task_id,
                    "total_time_seconds": round(gen_duration, 2),
                    "execution_time_ms": execution_time,
                    "result_size_kb": round(len(image_bytes) / 1024, 2),
                    "cloudfront_url": image_url,
                }
            )

            # Return BOTH bytes and CloudFront URL
            return (image_bytes, image_url)  # ← CHANGE THIS LINE
            
        except httpx.HTTPStatusError as e:
            logger.error(
                f"❌ WaveSpeed HTTP Error: {e.response.status_code} - {e.response.text[:500]}",
                extra={
                    "model": model_name,
                    "status": e.response.status_code,
                    "response": e.response.text[:500],
                }
            )
            raise ProviderError(
                "wavespeed",
                f"HTTP {e.response.status_code}: {e.response.text}",
                e.response.status_code
            )
        except Exception as e:
            logger.error(
                f"❌ WaveSpeed unexpected error: {type(e).__name__}: {str(e)}",
                extra={"model": model_name, "error": str(e)}
            )
            raise
    
    async def _poll_for_result(
        self,
        task_id: str,
        model_name: str,
        max_wait: Optional[int] = None,
        poll_interval: int = 2,
    ) -> tuple[str, int]:
        """Poll for task completion.
        
        Returns:
            Tuple of (image_url, execution_time_ms)
        """
        # ✅ Use config value if not explicitly provided
        if max_wait is None:
            from ..utils.config import get_config
            config = get_config()
            max_wait = int(config.timeout_wavespeed_seconds)  # Use existing timeout_wavespeed_seconds
        
        start_time = time.time()
        poll_count = 0
        
        while time.time() - start_time < max_wait:
            poll_count += 1
            elapsed = time.time() - start_time
            
            try:
                response = await self.client.get(
                    f"{self.base_url}/predictions/{task_id}/result",
                )
                
                if response.status_code != 200:
                    await asyncio.sleep(poll_interval)
                    continue
                
                result = response.json()
                
                if result.get("code") != 200:
                    await asyncio.sleep(poll_interval)
                    continue
                
                data = result.get("data", {})
                status = data.get("status")
                
                logger.info(
                    f"⏳ POLLING - {status}",
                    extra={
                        "task_id": task_id,
                        "status": status,
                        "elapsed_seconds": round(elapsed, 1),
                        "poll_count": poll_count,
                    }
                )
                
                if status == "completed":
                    outputs = data.get("outputs", [])
                    if not outputs:
                        raise ProviderError("wavespeed", "No outputs in completed task")
                    
                    image_url = outputs[0]
                    execution_time = data.get("executionTime", 0)
                    
                    logger.info(
                        f"✅ Task completed in {execution_time}ms",
                        extra={
                            "model": model_name,
                            "task_id": task_id,
                            "execution_time_ms": execution_time,
                            "total_poll_time_seconds": round(elapsed, 2),
                        }
                    )
                    
                    return (image_url, execution_time)
                
                elif status == "failed":
                    error = data.get("error", "Unknown error")
                    raise ProviderError("wavespeed", f"Task failed: {error}")
                
                await asyncio.sleep(poll_interval)
                
            except httpx.HTTPStatusError:
                await asyncio.sleep(poll_interval)
        
        raise ProviderError("wavespeed", f"Task timeout after {max_wait}s")
    
    async def _download_image(self, url: str) -> bytes:
        """Download image from URL."""
        try:
            logger.info(f"📥 Downloading image from: {url[:100]}")
            response = await self.client.get(url)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"❌ Download failed: {e}")
            raise ProviderError("wavespeed", f"Download failed: {e}")
