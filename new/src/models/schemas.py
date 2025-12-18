"""Pydantic schemas for data validation."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

from .enums import ProcessStatus, ValidationStatus, TaskType


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


# === V2.0 SIMPLIFIED CLASSIFIER SCHEMAS ===

class ClassifiedImage(BaseModel):
    """Simple image description from classifier."""
    index: int
    description: str


class ExtractedLayout(BaseModel):
    """Layout extracted from sketch."""
    from_index: int
    positions: str


class ExtractedStyle(BaseModel):
    """Style extracted from inspiration image."""
    from_index: int
    style: str


class ClassifiedBrief(BaseModel):
    """Parsed brief information."""
    summary: str
    text_content: List[str] = Field(default_factory=list)
    style_hints: Optional[str] = None


class ClassifiedTask(BaseModel):
    """Simplified classified task from classifier."""
    task_type: TaskType
    dimensions: List[str] = Field(default_factory=list)
    brief: ClassifiedBrief
    fonts: Optional[str] = None
    images: List[ClassifiedImage] = Field(default_factory=list)
    extracted_layout: Optional[ExtractedLayout] = None
    extracted_style: Optional[ExtractedStyle] = None
    website_url: Optional[str] = None
    brand_aesthetic: Optional[Dict[str, Any]] = None  # Filled by BrandAnalyzer