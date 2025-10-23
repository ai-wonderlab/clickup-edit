"""Custom exception classes for the image edit agent."""


class ImageEditAgentError(Exception):
    """Base exception for all agent errors."""
    pass


class ConfigurationError(ImageEditAgentError):
    """Configuration or initialization errors."""
    pass


class APIError(ImageEditAgentError):
    """Base class for API-related errors."""
    pass


class OpenRouterError(APIError):
    """OpenRouter API errors."""
    pass


class WaveSpeedAIError(APIError):
    """WaveSpeedAI API errors."""
    pass


class ClickUpError(APIError):
    """ClickUp API errors."""
    pass


class EnhancementError(ImageEditAgentError):
    """Errors during prompt enhancement."""
    pass


class GenerationError(ImageEditAgentError):
    """Errors during image generation."""
    pass


class ValidationError(ImageEditAgentError):
    """Errors during image validation."""
    pass


class AllEnhancementsFailed(EnhancementError):
    """All parallel enhancements failed."""
    pass


class AllGenerationsFailed(GenerationError):
    """All parallel generations failed."""
    pass


class AllValidationsFailed(ValidationError):
    """All parallel validations failed."""
    pass


class MaxIterationsExceeded(ImageEditAgentError):
    """Maximum refinement iterations exceeded."""
    pass


class WebhookValidationError(ImageEditAgentError):
    """Webhook signature validation failed."""
    pass


class ImageProcessingError(ImageEditAgentError):
    """Error processing image data."""
    pass


class TimeoutError(ImageEditAgentError):
    """Operation exceeded timeout."""
    pass
class ProviderError(APIError):
    """Generic provider API error with status code."""
    
    def __init__(self, provider: str, message: str, status_code: int = None):
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"{provider} error: {message}")


class AuthenticationError(ProviderError):
    """API authentication failed."""
    
    def __init__(self, provider: str):
        super().__init__(provider, "Authentication failed", 401)


class RateLimitError(ProviderError):
    """API rate limit exceeded."""
    
    def __init__(self, provider: str, retry_after: int = None):
        self.retry_after = retry_after
        message = f"Rate limit exceeded"
        if retry_after:
            message += f", retry after {retry_after}s"
        super().__init__(provider, message, 429)

class ImageFormatError(Exception):
    """Base error for format issues"""
    pass

class UnsupportedFormatError(ImageFormatError):
    """Format not supported"""
    pass

class ImageConversionError(ImageFormatError):
    """Conversion failed"""
    pass