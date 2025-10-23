"""Image format converter - converts any supported format to PNG."""

import io
from typing import Tuple
from PIL import Image

from .logger import get_logger
from .errors import UnsupportedFormatError, ImageConversionError

logger = get_logger(__name__)


class ImageConverter:
    """Convert any supported image format to PNG for processing."""
    
    # Formats that Pillow handles natively
    PILLOW_FORMATS = {
        'jpeg', 'jpg', 'png', 'webp', 'gif', 'bmp', 'tiff', 'tif', 'ico'
    }
    
    # Formats that need special handling
    SPECIAL_FORMATS = {
        'pdf',  # PyMuPDF
        'psd',  # psd-tools
    }
    
    @property
    def supported_formats(self) -> set:
        """All supported formats."""
        return self.PILLOW_FORMATS | self.SPECIAL_FORMATS
    
    async def convert_to_png(
        self,
        file_bytes: bytes,
        filename: str
    ) -> Tuple[bytes, str]:
        """
        Convert any supported format to PNG.
        
        Args:
            file_bytes: Raw file bytes
            filename: Original filename (to detect extension)
            
        Returns:
            Tuple of (png_bytes, new_filename)
            
        Raises:
            UnsupportedFormatError: If format not supported
            ImageConversionError: If conversion fails
        """
        # Extract extension
        extension = filename.lower().split('.')[-1]
        
        # Check if supported
        if extension not in self.supported_formats:
            supported_list = ', '.join(sorted(self.supported_formats))
            raise UnsupportedFormatError(
                f"Format '.{extension}' not supported. "
                f"Supported formats: {supported_list}"
            )
        
        logger.info(
            f"Converting {extension.upper()} to PNG",
            extra={
                "original_format": extension,
                "file_size_kb": len(file_bytes) / 1024,
            }
        )
        
        try:
            # Route to appropriate converter
            if extension == 'pdf':
                png_bytes = await self._convert_pdf(file_bytes)
            elif extension == 'psd':
                png_bytes = await self._convert_psd(file_bytes)
            else:
                # Standard Pillow conversion
                png_bytes = await self._convert_raster(file_bytes, extension)
            
            # Generate new filename
            base_name = '.'.join(filename.split('.')[:-1])
            new_filename = f"{base_name}.png"
            
            logger.info(
                f"Conversion successful: {extension.upper()} → PNG",
                extra={
                    "original_size_kb": len(file_bytes) / 1024,
                    "png_size_kb": len(png_bytes) / 1024,
                    "compression_ratio": f"{len(png_bytes)/len(file_bytes)*100:.1f}%",
                }
            )
            
            return png_bytes, new_filename
            
        except (UnsupportedFormatError, ImageConversionError):
            raise  # Re-raise our errors
        except Exception as e:
            logger.error(
                f"Conversion failed for {extension.upper()}",
                extra={
                    "format": extension,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )
            raise ImageConversionError(
                f"Failed to convert {extension.upper()} to PNG: {str(e)}"
            )
    
    async def _convert_raster(self, file_bytes: bytes, extension: str) -> bytes:
        """
        Convert common raster formats using Pillow.
        
        Handles: JPEG, PNG, WebP, GIF, BMP, TIFF, ICO
        """
        try:
            # Open image
            image = Image.open(io.BytesIO(file_bytes))
            
            # Convert color mode if needed
            # PNG supports RGB and RGBA
            if image.mode not in ('RGB', 'RGBA'):
                if image.mode == 'P':
                    # Palette mode - convert to RGBA to preserve transparency
                    image = image.convert('RGBA')
                else:
                    # CMYK, L (grayscale), etc. - convert to RGB
                    image = image.convert('RGB')
            
            # Save as PNG
            output = io.BytesIO()
            image.save(output, format='PNG', optimize=True)
            
            return output.getvalue()
            
        except Exception as e:
            raise ImageConversionError(
                f"Pillow conversion failed for {extension.upper()}: {str(e)}"
            )
    
    async def _convert_pdf(self, file_bytes: bytes) -> bytes:
        """
        Convert first page of PDF to PNG using PyMuPDF.
        
        High resolution (2x scale) for quality preservation.
        """
        try:
            import fitz  # PyMuPDF
            
            # Open PDF
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            
            if len(doc) == 0:
                raise ImageConversionError("PDF has no pages")
            
            if len(doc) > 1:
                logger.warning(
                    f"PDF has {len(doc)} pages, using only first page",
                    extra={"page_count": len(doc)}
                )
            
            # Get first page at high resolution
            page = doc[0]
            matrix = fitz.Matrix(2, 2)  # 2x scale for quality
            pix = page.get_pixmap(matrix=matrix)
            
            # Convert to PNG bytes
            png_bytes = pix.tobytes(output="png")
            
            doc.close()
            
            return png_bytes
            
        except ImportError:
            raise ImageConversionError(
                "PyMuPDF not installed. Install with: pip install PyMuPDF"
            )
        except Exception as e:
            raise ImageConversionError(f"PDF conversion failed: {str(e)}")
    
    async def _convert_psd(self, file_bytes: bytes) -> bytes:
        """
        Convert PSD to PNG using psd-tools.
        
        Flattens all layers into single image.
        """
        try:
            from psd_tools import PSDImage
            
            # Open PSD
            psd = PSDImage.open(io.BytesIO(file_bytes))
            
            # Flatten all layers to PIL Image
            image = psd.topil()
            
            # Save as PNG
            output = io.BytesIO()
            image.save(output, format='PNG', optimize=True)
            
            return output.getvalue()
            
        except ImportError:
            raise ImageConversionError(
                "psd-tools not installed. Install with: pip install psd-tools"
            )
        except Exception as e:
            raise ImageConversionError(f"PSD conversion failed: {str(e)}")
    
    def get_format_info(self, filename: str) -> dict:
        """
        Get information about a file format.
        
        Returns:
            Dict with format metadata
        """
        extension = filename.lower().split('.')[-1]
        
        return {
            "extension": extension,
            "supported": extension in self.supported_formats,
            "converter": self._get_converter_name(extension),
            "description": self._get_format_description(extension),
        }
    
    def _get_converter_name(self, extension: str) -> str:
        """Get the converter used for this format."""
        if extension in self.PILLOW_FORMATS:
            return "Pillow (PIL)"
        elif extension == 'pdf':
            return "PyMuPDF (fitz)"
        elif extension == 'psd':
            return "psd-tools"
        else:
            return "Unknown"
    
    def _get_format_description(self, extension: str) -> str:
        """Get human-readable format description."""
        descriptions = {
            'jpeg': 'JPEG compressed photo',
            'jpg': 'JPEG compressed photo',
            'png': 'PNG with transparency',
            'webp': 'Modern web format',
            'gif': 'Animated or simple graphics',
            'bmp': 'Uncompressed bitmap',
            'tiff': 'High-quality print format',
            'tif': 'High-quality print format',
            'pdf': 'Adobe PDF document',
            'psd': 'Adobe Photoshop source file',
            'ico': 'Windows icon',
        }
        return descriptions.get(extension, f'.{extension} file')