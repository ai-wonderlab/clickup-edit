"""Health check endpoint."""

from fastapi import APIRouter
from datetime import datetime

from ..utils.config_manager import config_manager

router = APIRouter()


@router.get("/")
async def health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "service": "image-edit-agent",
        "version": "1.0.0",
    }


@router.get("/ready")
async def readiness_check():
    """Readiness check for Kubernetes/Railway."""
    # Could add more checks here (DB, external APIs, etc.)
    return {
        "ready": True,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/detailed")
async def health_detailed():
    """Detailed health check with config source information."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "service": "image-edit-agent",
        "version": "1.0.0",
        "supabase_connected": config_manager.is_supabase_connected,
        "config_source": "supabase" if config_manager.is_supabase_connected else "yaml",
        "active_models": config_manager.get_active_models(),
        "prompts_loaded": len(config_manager.list_prompts()),
    }