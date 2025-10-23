"""Health check endpoint."""

from fastapi import APIRouter
from datetime import datetime

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