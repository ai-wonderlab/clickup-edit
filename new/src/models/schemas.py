"""Pydantic schemas for data validation."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

from .enums import ProcessStatus, ValidationStatus, TaskType, AttachmentIntent


class EnhancedPrompt(BaseModel):
    """Result of prompt enhancement."""
    model_name: str
    original: str
    enhanced: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class GeneratedImage(BaseModel):
    """Result of image generation."""
    model_name: str
    image_bytes: bytes
    temp_url: str
    original_image_url: str
    prompt_used: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        arbitrary_types_allowed = True


class ValidationResult(BaseModel):
    """Result of image validation."""
    model_name: str
    passed: bool
    score: int  # 0-100
    issues: List[str] = Field(default_factory=list)
    reasoning: str
    status: ValidationStatus = ValidationStatus.PASS
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ProcessResult(BaseModel):
    """Final result of edit processing."""
    status: ProcessStatus
    final_image: Optional[GeneratedImage] = None
    iterations: int
    model_used: Optional[str] = None
    all_results: Optional[List[ValidationResult]] = None
    error: Optional[str] = None
    processing_time_seconds: Optional[float] = None


class RefineResult(BaseModel):
    """Result of refinement iteration."""
    enhanced: List[EnhancedPrompt]
    generated: List[GeneratedImage]
    validated: List[ValidationResult]
    refined_prompt: str


class ClickUpAttachment(BaseModel):
    """ClickUp attachment metadata."""
    id: str
    date: Optional[int] = None
    title: Optional[str] = None
    url: Optional[str] = None
    extension: Optional[str] = None


class ClickUpTask(BaseModel):
    """ClickUp task data."""
    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    attachments: List[ClickUpAttachment] = Field(default_factory=list)
    custom_fields: Optional[List[Dict[str, Any]]] = None


class WebhookPayload(BaseModel):
    """ClickUp webhook payload."""
    event: str
    task_id: str
    task: ClickUpTask
    webhook_id: Optional[str] = None


class IterationMetrics(BaseModel):
    """Metrics for a single iteration."""
    iteration_number: int
    enhancements_successful: int
    generations_successful: int
    validations_passed: int
    best_score: Optional[int] = None
    duration_seconds: float
    errors: List[str] = Field(default_factory=list)


# === V2.0 CLASSIFIER SCHEMAS ===

class ClassifiedAttachment(BaseModel):
    """Attachment with role and intent assigned by classifier."""
    index: int
    filename: str
    role: str  # Free: "logo", "product_photo", "inspiration", "layout_guide"
    intent: AttachmentIntent
    description: Optional[str] = None
    extracted_style: Optional[Dict[str, Any]] = None
    extracted_layout: Optional[Dict[str, Any]] = None


class TextElement(BaseModel):
    """Text element with hierarchy role."""
    content: str
    role: str  # "headline", "subtext", "discount", "cta"
    style_hint: Optional[str] = None


class BrandAesthetic(BaseModel):
    """Brand aesthetic extracted from website."""
    style: Optional[str] = None
    typography: Optional[str] = None
    colors: Optional[str] = None
    layout_pattern: Optional[str] = None
    mood: Optional[str] = None


class ClassifiedTask(BaseModel):
    """Complete classified task from brief + attachments."""
    # Routing
    task_type: TaskType
    attachments: List[ClassifiedAttachment] = Field(default_factory=list)
    dimensions: List[str] = Field(default_factory=lambda: ["1:1"])
    
    # Content
    text_elements: List[TextElement] = Field(default_factory=list)
    
    # Visual direction
    style_hints: Optional[Dict[str, Any]] = None
    color_scheme: Optional[Dict[str, Any]] = None
    typography: Optional[str] = None
    layout_instructions: Optional[Dict[str, Any]] = None
    background_type: Optional[str] = None
    
    # External
    website_url: Optional[str] = None
    brand_aesthetic: Optional[Dict[str, Any]] = None  # Dict from BrandAnalyzer
    
    # Fallback
    original_brief: str
    extra: Optional[Dict[str, Any]] = None