"""Brand analyzer using Claude with web search to extract brand aesthetics."""

import json
import re
import time
from typing import Optional
from pathlib import Path

from ..providers.openrouter import OpenRouterClient
from ..utils.logger import get_logger

logger = get_logger(__name__)


class BrandAnalyzer:
    """Analyzes brand websites using Claude with web search."""
    
    def __init__(self, openrouter_client: OpenRouterClient):
        """
        Initialize brand analyzer.
        
        Args:
            openrouter_client: OpenRouter API client for Claude calls
        """
        self.client = openrouter_client
        self.prompt_template = self._load_prompt()
    
    def _load_prompt(self) -> str:
        """Load brand analyzer prompt from file."""
        prompt_path = Path("config/prompts/brand_analyzer_prompt.txt")
        
        if not prompt_path.exists():
            logger.error(f"Brand analyzer prompt not found: {prompt_path}")
            raise FileNotFoundError(f"Brand analyzer prompt not found: {prompt_path}")
        
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    
    async def analyze(self, website_url: str) -> Optional[dict]:
        """
        Analyze brand website and extract aesthetic guidelines.
        
        Uses Claude with web search to fetch and analyze the website.
        
        Args:
            website_url: Brand website URL (e.g., "enzzo.gr")
            
        Returns:
            Brand aesthetic dict or None if analysis fails
        """
        logger.info("")
        logger.info("=" * 80)
        logger.info("🌐 BRAND ANALYZER START")
        logger.info("=" * 80)
        
        logger.info(
            "📥 BRAND ANALYZER INPUT",
            extra={"website_url": website_url}
        )
        
        try:
            # Normalize URL
            url = self._normalize_url(website_url)
            logger.info(f"🔗 NORMALIZED URL: {url}")
            
            # Call Claude with web search
            api_start = time.time()
            response = await self._call_claude_with_search(url)
            api_duration = time.time() - api_start
            
            # ============================================
            # RAW RESPONSE
            # ============================================
            logger.info(
                "📤 BRAND ANALYZER RAW RESPONSE",
                extra={
                    "api_duration_seconds": round(api_duration, 2),
                    "response_length": len(response),
                    "response_full": response,
                }
            )
            
            # Parse response
            result = self._parse_response(response)
            
            # ============================================
            # PARSED RESULT
            # ============================================
            logger.info("")
            logger.info("-" * 60)
            logger.info("🌐 BRAND ANALYSIS RESULT")
            logger.info("-" * 60)
            
            logger.info(
                "🎨 BRAND AESTHETIC",
                extra={
                    "brand_aesthetic": result.get("brand_aesthetic"),
                    "prompt_guidance": result.get("prompt_guidance"),
                }
            )
            
            logger.info("")
            logger.info("=" * 80)
            logger.info("🌐 BRAND ANALYZER COMPLETE")
            logger.info("=" * 80)
            
            return result
            
        except Exception as e:
            logger.error(
                f"Brand analysis failed: {e}",
                extra={"website_url": website_url, "error": str(e)},
                exc_info=True
            )
            return None
    
    def _normalize_url(self, url: str) -> str:
        """
        Normalize URL to full format.
        
        Args:
            url: Raw URL (might be just domain)
            
        Returns:
            Full URL with https://
        """
        url = url.strip()
        
        # Remove any existing protocol
        url = re.sub(r'^https?://', '', url)
        url = re.sub(r'^www\.', '', url)
        
        # Add https://
        return f"https://{url}"
    
    async def _call_claude_with_search(self, url: str) -> str:
        """
        Call Claude with web search enabled to analyze website.
        
        Args:
            url: Full website URL
            
        Returns:
            Raw JSON response string
        """
        # Build user message
        user_message = f"""Analyze this brand's website and extract their visual style guidelines.

WEBSITE URL: {url}

Please search/visit the website to understand their:
- Visual style and mood
- Typography patterns
- Color usage
- Layout preferences
- How they present promotions/sales

Then return the analysis in the JSON format specified."""

        # Build messages
        messages = [
            {
                "role": "system",
                "content": self.prompt_template
            },
            {
                "role": "user",
                "content": user_message
            }
        ]
        
        # Call Claude via OpenRouter with web search enabled
        payload = {
            "model": "anthropic/claude-sonnet-4.5:online",  # :online enables web search
            "messages": messages,
            "max_tokens": 2000,
            "temperature": 0.0,
            # OpenRouter web search plugin with native Claude search
            "plugins": [
                {
                    "id": "web",
                    "engine": "native",  # Uses Anthropic's native web search
                    "max_results": 5
                }
            ]
        }
        
        response = await self.client.client.post(
            f"{self.client.base_url}/chat/completions",
            json=payload,
            timeout=60.0,  # Longer timeout for web search
        )
        
        self.client._handle_response_errors(response)
        
        data = response.json()
        
        # Extract content from response
        # May have multiple content blocks due to tool use
        content_parts = []
        for choice in data.get("choices", []):
            message = choice.get("message", {})
            content = message.get("content", "")
            
            if isinstance(content, str):
                content_parts.append(content)
            elif isinstance(content, list):
                # Handle content blocks
                for block in content:
                    if block.get("type") == "text":
                        content_parts.append(block.get("text", ""))
        
        full_content = "\n".join(content_parts)
        
        logger.info(
            "Claude brand analysis response received",
            extra={"response_length": len(full_content)}
        )
        
        return full_content
    
    def _parse_response(self, response: str) -> dict:
        """
        Parse Claude's JSON response.
        
        Args:
            response: Raw response string (may contain JSON)
            
        Returns:
            Parsed brand aesthetic dict
        """
        # Strip markdown code blocks if present
        response = re.sub(r'```json\s*', '', response)
        response = re.sub(r'```\s*$', '', response)
        response = response.strip()
        
        # Find JSON object in response
        # Look for outermost braces
        brace_count = 0
        start_idx = -1
        end_idx = -1
        
        for i, char in enumerate(response):
            if char == '{':
                if brace_count == 0:
                    start_idx = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i
                    break
        
        if start_idx != -1 and end_idx != -1:
            json_str = response[start_idx:end_idx + 1]
            return json.loads(json_str)
        
        # If no JSON found, return empty structure
        logger.warning("No JSON found in brand analysis response")
        return {
            "brand_aesthetic": {
                "style": "unknown",
                "mood": "unknown",
            },
            "prompt_guidance": ""
        }
