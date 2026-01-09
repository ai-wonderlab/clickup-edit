"""Task parser - extracts structured data from ClickUp custom fields.

Deterministic field parsing for task routing.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ParsedAttachment:
    """Single attachment from a Files custom field."""
    url: str
    filename: str
    
    
@dataclass
class ParsedTask:
    """Structured task data extracted from ClickUp custom fields."""
    
    # Core routing
    task_type: str  # "Edit" or "Creative"
    
    # Content
    main_text: Optional[str] = None
    secondary_text: Optional[str] = None
    font: Optional[str] = None
    style_direction: Optional[str] = None
    extra_notes: Optional[str] = None
    brand_website: Optional[str] = None
    
    # Dimensions
    dimensions: List[str] = field(default_factory=list)
    
    # Attachments (typed)
    logo: List[ParsedAttachment] = field(default_factory=list)
    main_image: List[ParsedAttachment] = field(default_factory=list)
    reference_images: List[ParsedAttachment] = field(default_factory=list)
    additional_images: List[ParsedAttachment] = field(default_factory=list)
    
    @property
    def is_edit(self) -> bool:
        return self.task_type == "Edit"
    
    @property
    def is_creative(self) -> bool:
        return self.task_type == "Creative"
    
    @property
    def all_images(self) -> List[ParsedAttachment]:
        """All images in order: main, additional, reference."""
        return self.main_image + self.additional_images + self.reference_images
    
    @property
    def generation_images(self) -> List[ParsedAttachment]:
        """Images for generation (excludes reference)."""
        return self.main_image + self.additional_images
    

class TaskParser:
    """Parses ClickUp task custom fields into structured data."""
    
    # Field name mapping (ClickUp field name -> attribute name)
    FIELD_MAP = {
        "Task Type": "task_type",
        "Main Text": "main_text",
        "Secondary Text": "secondary_text",
        "Font": "font",
        "Style Direction": "style_direction",
        "Extra Notes": "extra_notes",
        "Brand Website": "brand_website",
        "Dimensions": "dimensions",
        "Logo": "logo",
        "Main Image": "main_image",
        "Reference Images": "reference_images",
        "Additional Images": "additional_images",
    }
    
    def parse(self, task_data: Dict[str, Any]) -> ParsedTask:
        """
        Parse ClickUp task data into structured ParsedTask.
        
        Args:
            task_data: Raw task data from ClickUp API
            
        Returns:
            ParsedTask with all fields populated
        """
        custom_fields = task_data.get("custom_fields", [])
        
        logger.info(
            "Parsing task custom fields",
            extra={"field_count": len(custom_fields)}
        )
        
        # Build field lookup by name
        fields_by_name = {f["name"]: f for f in custom_fields}
        
        # Extract each field
        parsed = ParsedTask(
            task_type=self._parse_dropdown(fields_by_name.get("Task Type")),
            main_text=self._parse_text(fields_by_name.get("Main Text")),
            secondary_text=self._parse_text(fields_by_name.get("Secondary Text")),
            font=self._parse_text(fields_by_name.get("Font")),
            style_direction=self._parse_text(fields_by_name.get("Style Direction")),
            extra_notes=self._parse_text(fields_by_name.get("Extra Notes")),
            brand_website=self._parse_url(fields_by_name.get("Brand Website")),
            dimensions=self._parse_labels(fields_by_name.get("Dimensions")),
            logo=self._parse_attachments(fields_by_name.get("Logo")),
            main_image=self._parse_attachments(fields_by_name.get("Main Image")),
            reference_images=self._parse_attachments(fields_by_name.get("Reference Images")),
            additional_images=self._parse_attachments(fields_by_name.get("Additional Images")),
        )
        
        logger.info(
            "Task parsed successfully",
            extra={
                "task_type": parsed.task_type,
                "has_main_text": parsed.main_text is not None,
                "dimensions": parsed.dimensions,
                "main_image_count": len(parsed.main_image),
                "reference_count": len(parsed.reference_images),
                "has_website": parsed.brand_website is not None,
            }
        )
        
        return parsed
    
    def _parse_dropdown(self, field: Optional[Dict]) -> str:
        """Parse dropdown field to option name."""
        if not field:
            return "Edit"  # Default
        
        value = field.get("value")
        if value is None:
            return "Edit"
        
        # Value is index into options array
        options = field.get("type_config", {}).get("options", [])
        
        if isinstance(value, int) and 0 <= value < len(options):
            return options[value].get("name", "Edit")
        
        # If value is already the option ID, find it
        if isinstance(value, str):
            for opt in options:
                if opt.get("id") == value:
                    return opt.get("name", "Edit")
        
        return "Edit"
    
    def _parse_text(self, field: Optional[Dict]) -> Optional[str]:
        """Parse text/short_text field."""
        if not field:
            return None
        
        value = field.get("value")
        if not value:
            return None
        
        # Clean up whitespace and newlines
        return value.strip()
    
    def _parse_url(self, field: Optional[Dict]) -> Optional[str]:
        """Parse URL field."""
        if not field:
            return None
        
        value = field.get("value")
        if not value:
            return None
        
        return value.strip()
    
    def _parse_labels(self, field: Optional[Dict]) -> List[str]:
        """Parse labels (multi-select) field to list of label strings."""
        if not field:
            return []
        
        value = field.get("value")
        if not value:
            return []
        
        # Value is list of label IDs
        if not isinstance(value, list):
            return []
        
        # Build ID -> label mapping
        options = field.get("type_config", {}).get("options", [])
        id_to_label = {opt["id"]: opt["label"] for opt in options}
        
        # Map IDs to labels
        labels = []
        for label_id in value:
            if label_id in id_to_label:
                labels.append(id_to_label[label_id])
        
        return labels
    
    def _parse_attachments(self, field: Optional[Dict]) -> List[ParsedAttachment]:
        """Parse attachment/files field to list of ParsedAttachment."""
        if not field:
            return []
        
        value = field.get("value")
        if not value:
            return []
        
        if not isinstance(value, list):
            return []
        
        attachments = []
        for att in value:
            url = att.get("url")
            if url:
                attachments.append(ParsedAttachment(
                    url=url,
                    filename=att.get("title", "image.png"),
                ))
        
        return attachments
    
    def build_prompt(self, parsed: ParsedTask) -> str:
        """
        Build generation prompt from parsed task data.
        
        For EDIT: Simple instruction from extra_notes
        For CREATIVE: Full structured prompt
        
        Args:
            parsed: ParsedTask object
            
        Returns:
            Prompt string for AI generation
        """
        if parsed.is_edit:
            return self._build_edit_prompt(parsed)
        else:
            return self._build_creative_prompt(parsed)
    
    def _build_edit_prompt(self, parsed: ParsedTask) -> str:
        """Build prompt for simple edit task."""
        parts = []
        
        if parsed.extra_notes:
            parts.append(parsed.extra_notes)
        else:
            parts.append("Edit this image as requested.")
        
        # Add any specific instructions
        if parsed.main_text:
            parts.append(f"Text to add/change: {parsed.main_text}")
        
        return "\n".join(parts)
    
    def _build_creative_prompt(self, parsed: ParsedTask) -> str:
        """Build prompt for branded creative task."""
        parts = []
        
        # Dimension instruction
        if parsed.dimensions:
            dims = ", ".join(parsed.dimensions)
            parts.append(f"Create marketing graphics in these dimensions: {dims}")
        else:
            parts.append("Create a marketing graphic.")
        
        # Main text
        if parsed.main_text:
            parts.append(f"\nPrimary text: \"{parsed.main_text}\"")
        
        # Secondary text
        if parsed.secondary_text:
            parts.append(f"Secondary text: \"{parsed.secondary_text}\"")
        
        # Font
        if parsed.font:
            parts.append(f"\nFont: {parsed.font}")
        
        # Style direction
        if parsed.style_direction:
            parts.append(f"\nStyle direction: {parsed.style_direction}")
        
        # Extra notes
        if parsed.extra_notes:
            parts.append(f"\nAdditional instructions: {parsed.extra_notes}")
        
        # Reference images context
        if parsed.reference_images:
            parts.append(f"\nReference images provided for style/layout guidance.")
        
        return "\n".join(parts)