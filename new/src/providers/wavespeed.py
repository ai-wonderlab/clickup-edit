"""WaveSpeedAI API client - CORRECT implementation."""

import httpx
import asyncio
from typing import Optional, Dict, Any

from .base import BaseProvider
from ..utils.logger import get_logger
from ..utils.errors import ProviderError, AuthenticationError, RateLimitError
from ..utils.retry import retry_async

logger = get_logger(__name__)


class WaveSpeedAIClient(BaseProvider):
    """Client for WaveSpeedAI image editing API."""
    
    def __init__(self, api_key: str, timeout: Optional[float] = None):
        # ✅ NEW: Use config value if not explicitly provided
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
        original_image_url: str,
        model_name: str,
    ) -> tuple[bytes, str]:
        """Generate edited image using WaveSpeed API.
        
        Returns:
            Tuple of (image_bytes, cloudfront_url)
        """
        self._ensure_client()
        
        # CORRECT model mapping with REAL endpoints
        model_mapping = {
            "seedream-v4": "bytedance/seedream-v4/edit",
            "qwen-edit-plus": "wavespeed-ai/qwen-image/edit-plus",
            "wan-2.5-edit": "alibaba/wan-2.5/image-edit",
            "nano-banana": "google/nano-banana/edit",
            "nano-banana-pro": "google/nano-banana-pro/edit",  # ✅ NEW: Pro version
        }
        
        model_id = model_mapping.get(model_name, model_name)
        
        # CORRECT payload structure - uses "images" array!
        payload = {
            "images": [original_image_url],  # Array, not single string!
            "prompt": prompt,
            "enable_base64_output": False,
            "enable_sync_mode": False,
        }
        
        # Add model-specific parameters
        if "qwen" in model_name.lower():
            payload["seed"] = -1
            payload["output_format"] = "jpeg"
        elif "nano-banana-pro" in model_name.lower():
            # ✅ nano-banana-pro specific settings
            payload["output_format"] = "jpeg"  # JPEG much smaller than PNG (60-80% reduction)
            payload["resolution"] = "2k"  # 2K resolution
        elif "nano-banana" in model_name.lower():
            payload["output_format"] = "jpeg"
        elif "wan" in model_name.lower():
            payload["seed"] = -1
        
        try:
            logger.info(
                f"🚀 Submitting to WaveSpeed: {model_id}",
                extra={
                    "model": model_name,
                    "model_id": model_id,
                    "prompt": prompt[:100],
                    "image_url": original_image_url[:100],
                }
            )
            
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
                f"✅ Task submitted: {task_id}",
                extra={
                    "model": model_name,
                    "task_id": task_id,
                    "status": task_data.get("status"),
                }
            )
            
            # STEP 2: Poll for completion
            image_url = await self._poll_for_result(task_id, model_name)

            # STEP 3: Download image
            image_bytes = await self._download_image(image_url)

            logger.info(
                f"🎉 Image generated successfully!",
                extra={
                    "model": model_name,
                    "task_id": task_id,
                    "size_kb": len(image_bytes) / 1024,
                    "cloudfront_url": image_url,  # ← ADD THIS
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
    ) -> str:
        """Poll for task completion."""
        # ✅ NEW: Use config value if not explicitly provided
        if max_wait is None:
            from ..utils.config import get_config
            config = get_config()
            max_wait = config.timeout_wavespeed_polling_seconds
        
        import time
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
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
                    f"📊 Task status: {status}",
                    extra={"model": model_name, "task_id": task_id, "status": status}
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
                            "execution_time": execution_time,
                        }
                    )
                    
                    return image_url
                
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
