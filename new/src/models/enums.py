"""Enumerations for the Image Edit Agent."""

from enum import Enum


class ProcessStatus(str, Enum):
    """Status of edit processing."""
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    HYBRID_FALLBACK = "hybrid_fallback"
    TIMEOUT = "timeout"


class ValidationStatus(str, Enum):
    """Status of image validation."""
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


class ModelProvider(str, Enum):
    """Provider for AI models."""
    OPENROUTER = "openrouter"
    WAVESPEED = "wavespeed"
    CLICKUP = "clickup"


class IterationStage(str, Enum):
    """Stage of iteration processing."""
    ENHANCEMENT = "enhancement"
    GENERATION = "generation"
    VALIDATION = "validation"
    REFINEMENT = "refinement"
    DECISION = "decision"


class TaskType(str, Enum):
    """Type of task from custom fields."""
    SIMPLE_EDIT = "simple_edit"
    BRANDED_CREATIVE = "branded_creative"


class AttachmentIntent(str, Enum):
    """How attachment should be used."""
    INCLUDE_IN_OUTPUT = "include_in_output"
    REFERENCE_ONLY = "reference_only"