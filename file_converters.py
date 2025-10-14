"""
File Format Converters
Converts PDF, PSD, AI, and other formats to PNG for processing
"""
import os
import tempfile
from io import BytesIO
from PIL import Image
import logging

logger = logging.getLogger(__name__)

def convert_to_png(file_bytes, filename, mimetype=None):
    """
    Convert various file formats to PNG
    
    Args:
        file_bytes: Raw file bytes
        filename: Original filename (used to detect format)
        mimetype: Optional MIME type
        
    Returns:
        PNG image bytes or None if conversion fails
    """
    try:
        # Get file extension
        ext = os.path.splitext(filename.lower())[1]
        
        # If already an image format Pillow supports, just open it
        if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff']:
            logger.info(f"Direct image format: {ext}")
            return convert_image_to_png(file_bytes)
        
        # PDF conversion
        elif ext == '.pdf':
            logger.info("Converting PDF to PNG...")
            return convert_pdf_to_png(file_bytes)
        
        # PSD conversion
        elif ext == '.psd':
            logger.info("Converting PSD to PNG...")
            return convert_psd_to_png(file_bytes)
        
        # Try as image anyway (fallback)
        else:
            logger.warning(f"Unknown format {ext}, trying direct image conversion...")
            return convert_image_to_png(file_bytes)
            
    except Exception as e:
        logger.error(f"Error converting file: {e}")
        return None

def convert_image_to_png(image_bytes):
    """Convert standard image formats to PNG"""
    try:
        img = Image.open(BytesIO(image_bytes))
        
        # Convert to RGB if necessary (for transparency handling)
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Save as PNG
        output = BytesIO()
        img.save(output, format='PNG', optimize=True)
        output.seek(0)
        
        return output.read()
        
    except Exception as e:
        logger.error(f"Error converting image: {e}")
        return None

def convert_pdf_to_png(pdf_bytes):
    """Convert first page of PDF to PNG"""
    try:
        from pdf2image import convert_from_bytes
        
        # Convert first page only
        images = convert_from_bytes(pdf_bytes, first_page=1, last_page=1, dpi=300)
        
        if not images:
            logger.error("No images extracted from PDF")
            return None
        
        # Get first page
        img = images[0]
        
        # Convert to RGB
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Save as PNG
        output = BytesIO()
        img.save(output, format='PNG', optimize=True)
        output.seek(0)
        
        logger.info("PDF converted successfully")
        return output.read()
        
    except ImportError:
        logger.error("pdf2image not installed. Install with: pip install pdf2image")
        logger.error("Also requires poppler: brew install poppler (Mac) or apt-get install poppler-utils (Linux)")
        return None
    except Exception as e:
        logger.error(f"Error converting PDF: {e}")
        return None

def convert_psd_to_png(psd_bytes):
    """Convert PSD to PNG (flattened)"""
    try:
        from psd_tools import PSDImage
        
        # Load PSD
        psd = PSDImage.open(BytesIO(psd_bytes))
        
        # Convert to PIL Image (this flattens all layers)
        img = psd.topil()
        
        # Convert to RGB
        if img.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Save as PNG
        output = BytesIO()
        img.save(output, format='PNG', optimize=True)
        output.seek(0)
        
        logger.info("PSD converted successfully")
        return output.read()
        
    except ImportError:
        logger.error("psd-tools not installed. Install with: pip install psd-tools")
        return None
    except Exception as e:
        logger.error(f"Error converting PSD: {e}")
        return None

def get_supported_formats():
    """Return list of supported file formats"""
    return [
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff',  # Images
        '.pdf',  # PDF
        '.psd',  # Photoshop
    ]

def is_supported_format(filename):
    """Check if file format is supported"""
    ext = os.path.splitext(filename.lower())[1]
    return ext in get_supported_formats()