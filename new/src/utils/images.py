"""Image processing utilities."""

import base64
from io import BytesIO
from typing import Tuple
from PIL import Image

from .logger import get_logger
from .errors import ImageEditAgentError as ImageEditError

logger = get_logger(__name__)


def base64_to_bytes(base64_string: str) -> bytes:
    """
    Convert base64 string to bytes.
    
    Args:
        base64_string: Base64 encoded image
        
    Returns:
        Image bytes
    """
    # Remove data URL prefix if present
    if "," in base64_string:
        base64_string = base64_string.split(",")[1]
    
    return base64.b64decode(base64_string)


def bytes_to_base64(image_bytes: bytes) -> str:
    """
    Convert image bytes to base64 string.
    
    Args:
        image_bytes: Raw image bytes
        
    Returns:
        Base64 encoded string
    """
    return base64.b64encode(image_bytes).decode('utf-8')


def get_image_dimensions(image_bytes: bytes) -> Tuple[int, int]:
    """
    Get width and height of an image.
    
    Args:
        image_bytes: Raw image bytes
        
    Returns:
        Tuple of (width, height)
        
    Raises:
        ImageEditError: If image cannot be read
    """
    try:
        image = Image.open(BytesIO(image_bytes))
        return image.size
    except Exception as e:
        raise ImageEditError(f"Failed to read image dimensions: {e}")


def validate_image_format(image_bytes: bytes, allowed_formats: list = None) -> str:
    """
    Validate image format and return format name.
    
    Args:
        image_bytes: Raw image bytes
        allowed_formats: List of allowed formats (e.g., ['PNG', 'JPEG'])
        
    Returns:
        Image format (e.g., 'PNG')
        
    Raises:
        ImageEditError: If format is invalid or not allowed
    """
    if allowed_formats is None:
        allowed_formats = ['PNG', 'JPEG', 'JPG', 'WEBP']
    
    try:
        image = Image.open(BytesIO(image_bytes))
        image_format = image.format
        
        if image_format not in allowed_formats:
            raise ImageEditError(
                f"Invalid image format: {image_format}. "
                f"Allowed formats: {', '.join(allowed_formats)}"
            )
        
        return image_format
        
    except Exception as e:
        if isinstance(e, ImageEditError):
            raise
        raise ImageEditError(f"Failed to validate image format: {e}")


def resize_if_needed(
    image_bytes: bytes,
    max_width: int = 4096,
    max_height: int = 4096
) -> bytes:
    """
    Resize image if it exceeds maximum dimensions.
    
    Args:
        image_bytes: Raw image bytes
        max_width: Maximum width in pixels
        max_height: Maximum height in pixels
        
    Returns:
        Resized image bytes (or original if no resize needed)
    """
    try:
        image = Image.open(BytesIO(image_bytes))
        width, height = image.size
        
        # Check if resize needed
        if width <= max_width and height <= max_height:
            return image_bytes
        
        # Calculate new dimensions maintaining aspect ratio
        ratio = min(max_width / width, max_height / height)
        new_width = int(width * ratio)
        new_height = int(height * ratio)
        
        logger.info(
            f"Resizing image from {width}x{height} to {new_width}x{new_height}",
            extra={
                "original_width": width,
                "original_height": height,
                "new_width": new_width,
                "new_height": new_height,
            }
        )
        
        # Resize with high-quality resampling
        resized_image = image.resize((new_width, new_height), Image.LANCZOS)
        
        # Convert back to bytes
        buffer = BytesIO()
        resized_image.save(buffer, format=image.format)
        return buffer.getvalue()
        
    except Exception as e:
        logger.warning(f"Failed to resize image: {e}. Using original.")
        return image_bytes


def compress_if_needed(
    image_bytes: bytes,
    max_size_mb: float = 10.0,
    quality: int = 85
) -> bytes:
    """
    Compress image if file size exceeds maximum.
    
    Args:
        image_bytes: Raw image bytes
        max_size_mb: Maximum file size in MB
        quality: JPEG quality (0-100)
        
    Returns:
        Compressed image bytes (or original if no compression needed)
    """
    max_size_bytes = int(max_size_mb * 1024 * 1024)
    current_size = len(image_bytes)
    
    if current_size <= max_size_bytes:
        return image_bytes
    
    try:
        image = Image.open(BytesIO(image_bytes))
        
        logger.info(
            f"Compressing image from {current_size / 1024 / 1024:.2f}MB",
            extra={
                "original_size_mb": current_size / 1024 / 1024,
                "max_size_mb": max_size_mb,
                "quality": quality,
            }
        )
        
        # Compress
        buffer = BytesIO()
        image.save(buffer, format='JPEG', quality=quality, optimize=True)
        compressed_bytes = buffer.getvalue()
        
        logger.info(
            f"Compressed to {len(compressed_bytes) / 1024 / 1024:.2f}MB",
            extra={"compressed_size_mb": len(compressed_bytes) / 1024 / 1024}
        )
        
        return compressed_bytes
        
    except Exception as e:
        logger.warning(f"Failed to compress image: {e}. Using original.")
        return image_bytes


def resize_for_context(
    image_bytes: bytes,
    max_dimension: int = 512,
    quality: int = 70,
) -> bytes:
    """
    Resize image for Claude context (lower quality to save tokens).
    
    Args:
        image_bytes: Original image bytes
        max_dimension: Max width or height (default 512px)
        quality: JPEG quality 1-100 (default 70)
        
    Returns:
        Resized image bytes (JPEG)
    """
    try:
        image = Image.open(BytesIO(image_bytes))
        
        # Convert to RGB if needed (for JPEG)
        if image.mode in ('RGBA', 'P'):
            image = image.convert('RGB')
        
        width, height = image.size
        
        # Already small enough - just compress
        if max(width, height) <= max_dimension:
            buffer = BytesIO()
            image.save(buffer, format='JPEG', quality=quality)
            return buffer.getvalue()
        
        # Calculate new dimensions maintaining aspect ratio
        if width > height:
            new_width = max_dimension
            new_height = int(height * (max_dimension / width))
        else:
            new_height = max_dimension
            new_width = int(width * (max_dimension / height))
        
        # Resize with high-quality resampling
        img_resized = image.resize((new_width, new_height), Image.LANCZOS)
        
        # Convert to JPEG bytes
        buffer = BytesIO()
        img_resized.save(buffer, format='JPEG', quality=quality)
        
        logger.debug(
            f"Resized for context: {width}x{height} -> {new_width}x{new_height}",
            extra={
                "original_kb": len(image_bytes) / 1024,
                "resized_kb": len(buffer.getvalue()) / 1024,
            }
        )
        
        return buffer.getvalue()
        
    except Exception as e:
        logger.warning(f"Failed to resize image for context: {e}, using original")
        return image_bytes