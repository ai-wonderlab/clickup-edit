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