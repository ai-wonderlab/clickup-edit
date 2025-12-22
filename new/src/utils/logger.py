"""Structured logging utility with JSON output."""

import logging
import json
import sys
import os
from datetime import datetime
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """Format logs as JSON for structured logging."""
    
    # Fields that Python's logging adds automatically (exclude these)
    BUILTIN_ATTRS = {
        'name', 'msg', 'args', 'created', 'filename', 'funcName',
        'levelname', 'levelno', 'lineno', 'module', 'msecs',
        'pathname', 'process', 'processName', 'relativeCreated',
        'stack_info', 'exc_info', 'exc_text', 'thread', 'threadName',
        'taskName', 'message',
    }
    
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # ✅ Extract ALL extra fields dynamically
        for key, value in record.__dict__.items():
            if key not in self.BUILTIN_ATTRS and not key.startswith('_'):
                # ✅ Handle bytes - NEVER log raw bytes
                if isinstance(value, bytes):
                    log_data[key] = f"<bytes: {len(value)} bytes>"
                elif isinstance(value, (list, tuple)):
                    # Check for bytes in lists/tuples
                    sanitized = []
                    for item in value:
                        if isinstance(item, bytes):
                            sanitized.append(f"<bytes: {len(item)} bytes>")
                        else:
                            sanitized.append(item)
                    try:
                        json.dumps(sanitized)
                        log_data[key] = sanitized
                    except (TypeError, ValueError):
                        log_data[key] = str(sanitized)
                else:
                    try:
                        # Ensure JSON serializable
                        json.dumps(value)
                        log_data[key] = value
                    except (TypeError, ValueError):
                        # If not serializable, convert to string (truncate if too long)
                        str_value = str(value)
                        if len(str_value) > 500:
                            log_data[key] = str_value[:500] + "...[truncated]"
                        else:
                            log_data[key] = str_value
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Only configure if not already configured
    if not logger.handlers:
        # Get log level from environment
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, log_level))
        
        # Console handler with JSON formatting
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        
        # Prevent propagation to root logger
        logger.propagate = False
    
    return logger


# Create a default logger for the package
default_logger = get_logger("image_edit_agent")