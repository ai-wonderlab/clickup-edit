"""Task classifier - simplified version."""

import json
import time
from typing import List, Tuple
from pathlib import Path

from ..providers.openrouter import OpenRouterClient
from ..models.schemas import (
    ClassifiedTask,
    ClassifiedImage,
    ClassifiedBrief,
    ExtractedLayout,
    ExtractedStyle,
)
from ..models.enums import TaskType
from ..utils.logger import get_logger
from ..utils.config import load_fonts_guide

logger = get_logger(__name__)


class Classifier:
    """Classifies tasks using Claude vision - simplified."""
    
    def __init__(self, openrouter_client: OpenRouterClient):
        self.client = openrouter_client
        self.prompt_template = self._load_prompt()
    
    def _load_prompt(self) -> str:
        """Load classifier prompt and inject fonts guide."""
        prompt_path = Path("config/prompts/classifier_prompt.txt")
        
        if not prompt_path.exists():
            raise FileNotFoundError(f"Classifier prompt not found: {prompt_path}")
        
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt = f.read()
        
        # Inject fonts guide
        fonts_guide = load_fonts_guide()
        if fonts_guide and "{fonts_guide}" in prompt:
            prompt = prompt.replace("{fonts_guide}", fonts_guide)
            logger.info("Injected fonts guide into classifier prompt")
        
        return prompt
    
    async def classify(
        self,
        description: str,
        attachments: List[Tuple[str, bytes]],
    ) -> ClassifiedTask:
        """Classify task and extract information."""
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("🧠 CLASSIFIER START")
        logger.info("=" * 80)
        
        logger.info(
            "📥 CLASSIFIER INPUT",
            extra={
                "description_length": len(description),
                "description_full": description,
                "attachment_count": len(attachments),
                "attachments": [
                    {
                        "index": i,
                        "file_name": a[0],
                        "size_kb": round(len(a[1]) / 1024, 2),
                    }
                    for i, a in enumerate(attachments)
                ],
            }
        )
        
        try:
            classify_start = time.time()
            response = await self._call_claude(description, attachments)
            classify_duration = time.time() - classify_start
            
            logger.info(
                "📤 CLASSIFIER RAW RESPONSE",
                extra={
                    "api_duration_seconds": round(classify_duration, 2),
                    "response_length": len(response),
                    "response_full": response,
                }
            )
            
            classified = self._parse_response(response)
            
            logger.info("")
            logger.info("-" * 60)
            logger.info("🧠 CLASSIFICATION RESULT")
            logger.info("-" * 60)
            
            logger.info(
                "📊 CLASSIFIER COMPLETE",
                extra={
                    "task_type": classified.task_type.value,
                    "dimensions": classified.dimensions,
                    "brief_summary": classified.brief.summary,
                    "text_content": classified.brief.text_content,
                    "style_hints": classified.brief.style_hints,
                    "fonts": classified.fonts,
                    "image_count": len(classified.images),
                    "images": [
                        {"index": img.index, "description": img.description}
                        for img in classified.images
                    ],
                    "has_layout": classified.extracted_layout is not None,
                    "layout": classified.extracted_layout.positions if classified.extracted_layout else None,
                    "has_style": classified.extracted_style is not None,
                    "style_ref": classified.extracted_style.style if classified.extracted_style else None,
                    "website": classified.website_url,
                }
            )
            
            logger.info("")
            logger.info("=" * 80)
            logger.info("🧠 CLASSIFIER COMPLETE")
            logger.info("=" * 80)
            
            return classified
            
        except Exception as e:
            logger.error(f"Classification failed: {e}", exc_info=True)
            return self._fallback_classification(description, attachments)
    
    async def _call_claude(
        self,
        description: str,
        attachments: List[Tuple[str, bytes]],
    ) -> str:
        """Call Claude with vision."""
        import base64
        
        user_content = [
            {"type": "text", "text": f"USER REQUEST:\n{description}"}
        ]
        
        for i, (filename, img_bytes) in enumerate(attachments):
            img_b64 = base64.b64encode(img_bytes).decode('utf-8')
            user_content.append({
                "type": "text",
                "text": f"\n--- Image {i}: {filename} ---"
            })
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_b64}"}
            })
        
        messages = [
            {"role": "system", "content": self.prompt_template},
            {"role": "user", "content": user_content}
        ]
        
        payload = {
            "model": "anthropic/claude-sonnet-4",
            "messages": messages,
            "max_tokens": 2000,
            "temperature": 0.0,
        }
        
        response = await self.client.client.post(
            f"{self.client.base_url}/chat/completions",
            json=payload,
        )
        
        self.client._handle_response_errors(response)
        data = response.json()
        
        return data["choices"][0]["message"]["content"]
    
    def _parse_response(self, response: str) -> ClassifiedTask:
        """Parse Claude's JSON response."""
        import re
        
        # Strip markdown
        response = re.sub(r'```json\s*', '', response)
        response = re.sub(r'```\s*$', '', response)
        response = response.strip()
        
        data = json.loads(response)
        
        # Parse task type
        task_type_str = data.get("task_type", "SIMPLE_EDIT").upper()
        task_type = TaskType.BRANDED_CREATIVE if task_type_str == "BRANDED_CREATIVE" else TaskType.SIMPLE_EDIT
        
        # Parse brief
        brief_data = data.get("brief", {})
        brief = ClassifiedBrief(
            summary=brief_data.get("summary", ""),
            text_content=brief_data.get("text_content", []),
            style_hints=brief_data.get("style_hints"),
        )
        
        # Parse images
        images = [
            ClassifiedImage(index=img["index"], description=img["description"])
            for img in data.get("images", [])
        ]
        
        # Parse extracted layout
        extracted_layout = None
        if data.get("extracted_layout"):
            layout_data = data["extracted_layout"]
            extracted_layout = ExtractedLayout(
                from_index=layout_data.get("from_index", 0),
                positions=layout_data.get("positions", ""),
            )
        
        # Parse extracted style
        extracted_style = None
        if data.get("extracted_style"):
            style_data = data["extracted_style"]
            extracted_style = ExtractedStyle(
                from_index=style_data.get("from_index", 0),
                style=style_data.get("style", ""),
            )
        
        return ClassifiedTask(
            task_type=task_type,
            dimensions=data.get("dimensions", []),
            brief=brief,
            fonts=data.get("fonts"),
            images=images,
            primary_image_index=data.get("primary_image_index", 0),
            extracted_layout=extracted_layout,
            extracted_style=extracted_style,
            website_url=data.get("website_url"),
        )
    
    def _fallback_classification(
        self,
        description: str,
        attachments: List[Tuple[str, bytes]],
    ) -> ClassifiedTask:
        """Fallback when classification fails."""
        logger.warning("Using fallback classification")
        
        return ClassifiedTask(
            task_type=TaskType.SIMPLE_EDIT,
            dimensions=[],
            brief=ClassifiedBrief(
                summary=description,
                text_content=[],
                style_hints=None,
            ),
            fonts=None,
            images=[
                ClassifiedImage(index=i, description=f"Image {i}")
                for i in range(len(attachments))
            ],
            primary_image_index=0,
            extracted_layout=None,
            extracted_style=None,
            website_url=None,
        )
