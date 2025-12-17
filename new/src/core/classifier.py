"""Task classifier using Claude vision to analyze briefs and attachments."""

import json
import time
from typing import List, Tuple
from pathlib import Path

from ..providers.openrouter import OpenRouterClient
from ..models.schemas import (
    ClassifiedTask,
    ClassifiedAttachment,
    TextElement,
)
from ..models.enums import TaskType, AttachmentIntent
from ..utils.logger import get_logger
from ..utils.config import get_config, load_fonts_guide

logger = get_logger(__name__)


class Classifier:
    """Classifies tasks and attachments using Claude vision."""
    
    def __init__(self, openrouter_client: OpenRouterClient):
        """
        Initialize classifier.
        
        Args:
            openrouter_client: OpenRouter API client for Claude calls
        """
        self.client = openrouter_client
        self.prompt_template = self._load_prompt()
    
    def _load_prompt(self) -> str:
        """Load classifier prompt from file and inject fonts guide."""
        prompt_path = Path("config/prompts/classifier_prompt.txt")
        
        if not prompt_path.exists():
            logger.error(f"Classifier prompt not found: {prompt_path}")
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
        attachments: List[Tuple[str, bytes]],  # [(filename, png_bytes), ...]
    ) -> ClassifiedTask:
        """
        Classify task and attachments.
        
        Args:
            description: User's brief/request text
            attachments: List of (filename, image_bytes) tuples
            
        Returns:
            ClassifiedTask with all extracted information
        """
        logger.info("")
        logger.info("=" * 80)
        logger.info("🧠 CLASSIFIER START")
        logger.info("=" * 80)
        
        # ============================================
        # INPUT LOGGING
        # ============================================
        logger.info(
            "📥 CLASSIFIER INPUT",
            extra={
                "description_length": len(description),
                "description_full": description,
                "attachment_count": len(attachments),
                "attachments": [
                    {
                        "index": i,
                        "filename": a[0],
                        "size_kb": round(len(a[1]) / 1024, 2),
                    }
                    for i, a in enumerate(attachments)
                ],
            }
        )
        
        try:
            # Build message with images
            classify_start = time.time()
            response = await self._call_claude(description, attachments)
            classify_duration = time.time() - classify_start
            
            # ============================================
            # RAW RESPONSE LOGGING
            # ============================================
            logger.info(
                "📤 CLASSIFIER RAW RESPONSE",
                extra={
                    "api_duration_seconds": round(classify_duration, 2),
                    "response_length": len(response),
                    "response_full": response,
                }
            )
            
            # Parse response into ClassifiedTask
            classified = self._parse_response(response, description)
            
            # ============================================
            # FINAL RESULT LOGGING
            # ============================================
            logger.info("")
            logger.info("-" * 60)
            logger.info("🧠 CLASSIFICATION RESULT")
            logger.info("-" * 60)
            
            logger.info(
                f"📊 TASK TYPE: {classified.task_type.value}",
                extra={"task_type": classified.task_type.value}
            )
            
            logger.info(
                f"📐 DIMENSIONS: {classified.dimensions}",
                extra={
                    "dimensions": classified.dimensions,
                    "dimension_count": len(classified.dimensions),
                }
            )
            
            if classified.text_elements:
                logger.info(
                    f"📝 TEXT ELEMENTS: {len(classified.text_elements)}",
                    extra={
                        "text_elements": [
                            {
                                "role": te.role,
                                "content": te.content,
                                "style_hint": te.style_hint,
                            }
                            for te in classified.text_elements
                        ],
                    }
                )
            
            logger.info(
                f"🖼️ ATTACHMENTS CLASSIFIED: {len(classified.attachments)}",
                extra={
                    "attachments": [
                        {
                            "index": a.index,
                            "intent": a.intent.value,
                            "role": a.role,
                            "filename": a.filename,
                            "description": a.description,
                        }
                        for a in classified.attachments
                    ],
                }
            )
            
            if classified.website_url:
                logger.info(
                    f"🌐 WEBSITE DETECTED: {classified.website_url}",
                    extra={"website_url": classified.website_url}
                )
            
            if classified.style_hints:
                logger.info(
                    "🎨 STYLE HINTS",
                    extra={"style_hints": classified.style_hints}
                )
            
            if classified.color_scheme:
                logger.info(
                    "🎨 COLOR SCHEME",
                    extra={"color_scheme": classified.color_scheme}
                )
            
            if classified.typography:
                logger.info(
                    f"🔤 TYPOGRAPHY: {classified.typography}",
                    extra={"typography": classified.typography}
                )
            
            logger.info("")
            logger.info("=" * 80)
            logger.info("🧠 CLASSIFIER COMPLETE")
            logger.info("=" * 80)
            
            return classified
            
        except Exception as e:
            logger.error(
                f"Classification failed: {e}",
                extra={"error": str(e)},
                exc_info=True
            )
            
            # Fallback: SIMPLE_EDIT with first attachment
            return self._fallback_classification(description, attachments)
    
    async def _call_claude(
        self,
        description: str,
        attachments: List[Tuple[str, bytes]],
    ) -> str:
        """
        Call Claude with vision to classify.
        
        Args:
            description: User's brief
            attachments: List of (filename, bytes) tuples
            
        Returns:
            Raw JSON response string
        """
        import base64
        
        # Build user content with text + images
        user_content = [
            {
                "type": "text",
                "text": f"USER REQUEST:\n{description}\n\nIMAGES: {len(attachments)} attached"
            }
        ]
        
        # Add each image
        for i, (filename, img_bytes) in enumerate(attachments):
            img_b64 = base64.b64encode(img_bytes).decode('utf-8')
            user_content.append({
                "type": "text",
                "text": f"\n--- Image {i + 1}: {filename} ---"
            })
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_b64}"
                }
            })
        
        # Build messages
        messages = [
            {
                "role": "system",
                "content": self.prompt_template
            },
            {
                "role": "user",
                "content": user_content
            }
        ]
        
        # Call Claude via OpenRouter
        payload = {
            "model": "anthropic/claude-sonnet-4.5",
            "messages": messages,
            "max_tokens": 2000,
            "temperature": 0.0,  # Deterministic for classification
        }
        
        response = await self.client.client.post(
            f"{self.client.base_url}/chat/completions",
            json=payload,
        )
        
        self.client._handle_response_errors(response)
        
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        
        logger.info(
            "Claude classification response received",
            extra={"response_length": len(content)}
        )
        
        return content
    
    def _parse_response(
        self,
        response: str,
        original_brief: str,
    ) -> ClassifiedTask:
        """
        Parse Claude's JSON response into ClassifiedTask.
        
        Args:
            response: Raw JSON string from Claude
            original_brief: Original user request (for fallback)
            
        Returns:
            ClassifiedTask
        """
        import re
        
        # Strip markdown code blocks if present
        response = re.sub(r'```json\s*', '', response)
        response = re.sub(r'```\s*$', '', response)
        response = response.strip()
        
        # Parse JSON
        data = json.loads(response)
        
        # Parse attachments
        attachments = []
        for att in data.get("attachments", []):
            attachments.append(ClassifiedAttachment(
                index=att.get("index", 0),
                filename=att.get("filename", "unknown"),
                role=att.get("role", "unknown"),
                intent=AttachmentIntent(att.get("intent", "include_in_output")),
                description=att.get("description"),
                extracted_style=att.get("extracted_style"),
                extracted_layout=att.get("extracted_layout"),
            ))
        
        # Parse text elements
        text_elements = []
        for te in data.get("text_elements", []):
            if isinstance(te, dict):
                text_elements.append(TextElement(
                    content=te.get("content", ""),
                    role=te.get("role", "text"),
                    style_hint=te.get("style_hint"),
                ))
            elif isinstance(te, str):
                # Handle flat string format (backward compatibility)
                text_elements.append(TextElement(
                    content=te,
                    role="text",
                    style_hint=None,
                ))
        
        # Parse task type
        task_type_str = data.get("task_type", "SIMPLE_EDIT").upper()
        if task_type_str == "BRANDED_CREATIVE":
            task_type = TaskType.BRANDED_CREATIVE
        else:
            task_type = TaskType.SIMPLE_EDIT
        
        # Build ClassifiedTask
        return ClassifiedTask(
            task_type=task_type,
            attachments=attachments,
            dimensions=data.get("dimensions", ["1:1"]),
            text_elements=text_elements,
            style_hints=data.get("style_hints"),
            color_scheme=data.get("color_scheme"),
            typography=data.get("typography"),
            layout_instructions=data.get("layout_instructions"),
            background_type=data.get("background_type"),
            website_url=data.get("website_url"),
            brand_aesthetic=None,  # Filled later by BrandAnalyzer
            original_brief=original_brief,
            extra=data.get("extra"),
        )
    
    def _fallback_classification(
        self,
        description: str,
        attachments: List[Tuple[str, bytes]],
    ) -> ClassifiedTask:
        """
        Fallback classification when Claude fails.
        
        Defaults to SIMPLE_EDIT with first attachment.
        
        Args:
            description: Original brief
            attachments: List of attachments
            
        Returns:
            Safe fallback ClassifiedTask
        """
        logger.warning(
            "Using fallback classification",
            extra={"attachment_count": len(attachments)}
        )
        
        # Create basic attachment classification
        classified_attachments = []
        for i, (filename, _) in enumerate(attachments):
            classified_attachments.append(ClassifiedAttachment(
                index=i,
                filename=filename,
                role="graphic" if i == 0 else "unknown",
                intent=AttachmentIntent.INCLUDE_IN_OUTPUT if i == 0 else AttachmentIntent.REFERENCE_ONLY,
                description=None,
                extracted_style=None,
                extracted_layout=None,
            ))
        
        return ClassifiedTask(
            task_type=TaskType.SIMPLE_EDIT,
            attachments=classified_attachments,
            dimensions=["1:1"],
            text_elements=[],
            style_hints=None,
            color_scheme=None,
            typography=None,
            layout_instructions=None,
            background_type=None,
            website_url=None,
            brand_aesthetic=None,
            original_brief=description,
            extra={"fallback": True, "reason": "Classification failed"},
        )
