"""ClickUp webhook handler with per-task locking."""

import hmac
import hashlib
import asyncio
import time
from typing import Dict, Any, Tuple, Optional
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel

from ..models.schemas import WebhookPayload, ClickUpTask, ClickUpAttachment
from ..utils.logger import get_logger
from ..utils.config import get_config
from ..utils.image_converter import ImageConverter
from ..utils.errors import UnsupportedFormatError, ImageConversionError

logger = get_logger(__name__)

router = APIRouter()

# ============================================================================
# 📝 RESPONSE MODEL
# ============================================================================

class WebhookResponse(BaseModel):
    """Standard webhook response model."""
    status: str
    task_id: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    reason: Optional[str] = None

# ============================================================================
# 🔐 TASK-LEVEL LOCKING SYSTEM WITH TTL
# ============================================================================

# ✅ NEW: Locks with timestamps for TTL-based cleanup
_task_locks: Dict[str, Tuple[asyncio.Lock, float]] = {}
_locks_registry_lock = asyncio.Lock()  # Protects the registry itself

# ✅ Use defaults at module level (will be overridden from config at runtime)
LOCK_TTL_SECONDS = 3600  # 1 hour default
CLEANUP_CHECK_INTERVAL = 100  # Cleanup every 100 lock acquisitions


async def cleanup_stale_locks(force: bool = False) -> int:
    """
    Remove stale locks that are older than TTL.
    
    Args:
        force: If True, cleanup regardless of counter
        
    Returns:
        Number of locks cleaned up
    """
    async with _locks_registry_lock:
        now = time.time()
        
        # Find stale locks
        stale_task_ids = [
            task_id for task_id, (lock, timestamp) in _task_locks.items()
            if now - timestamp > LOCK_TTL_SECONDS
        ]
        
        # Remove stale locks
        for task_id in stale_task_ids:
            try:
                lock, timestamp = _task_locks[task_id]
                
                # Try to release if locked (defensive)
                if lock.locked():
                    lock.release()
                
                del _task_locks[task_id]
                
                age_minutes = (now - timestamp) / 60
                logger.warning(
                    f"Cleaned up stale lock for task {task_id}",
                    extra={
                        "task_id": task_id,
                        "age_minutes": age_minutes,
                        "reason": "Lock TTL exceeded"
                    }
                )
            except Exception as e:
                logger.error(
                    f"Error cleaning up lock for {task_id}: {e}",
                    extra={"task_id": task_id, "error": str(e)}
                )
        
        if stale_task_ids:
            logger.info(
                f"Cleanup complete: removed {len(stale_task_ids)} stale locks",
                extra={
                    "cleaned": len(stale_task_ids),
                    "remaining": len(_task_locks),
                }
            )
        
        return len(stale_task_ids)


# Counter for periodic cleanup
_acquire_counter = 0


async def acquire_task_lock(task_id: str) -> bool:
    """
    Try to acquire exclusive lock for a task_id with automatic cleanup.
    
    Automatically cleans up stale locks every CLEANUP_CHECK_INTERVAL acquisitions.
    
    Args:
        task_id: ClickUp task ID
        
    Returns:
        True if lock acquired (task can proceed)
        False if already locked (task already processing)
    """
    global _acquire_counter
    
    # ✅ PERIODIC CLEANUP: Every Nth acquisition (check before acquiring registry lock)
    should_cleanup = False
    async with _locks_registry_lock:
        _acquire_counter += 1
        if _acquire_counter % CLEANUP_CHECK_INTERVAL == 0:
            should_cleanup = True
            logger.info(
                f"Running periodic cleanup (acquisition #{_acquire_counter})",
                extra={
                    "total_locks": len(_task_locks),
                    "acquisition_count": _acquire_counter,
                }
            )
        
        # Check if task already has a lock
        if task_id in _task_locks:
            lock, timestamp = _task_locks[task_id]
            age_seconds = time.time() - timestamp
            
            # If lock is VERY old, might be stale even if still in dict
            if age_seconds > LOCK_TTL_SECONDS:
                logger.warning(
                    f"Found stale lock for {task_id}, cleaning up",
                    extra={
                        "task_id": task_id,
                        "age_seconds": age_seconds,
                    }
                )
                # Clean it up and allow re-acquisition
                try:
                    if lock.locked():
                        lock.release()
                    del _task_locks[task_id]
                except Exception as e:
                    logger.error(f"Error cleaning stale lock: {e}")
                # Fall through to create new lock
            else:
                # Lock exists and is not stale = task already processing
                logger.info(
                    "Task already processing, rejecting duplicate",
                    extra={
                        "task_id": task_id,
                        "lock_age_seconds": age_seconds,
                    }
                )
                return False
        
        # Create new lock with timestamp
        now = time.time()
        _task_locks[task_id] = (asyncio.Lock(), now)
        await _task_locks[task_id][0].acquire()
        
        logger.info(
            "Task lock acquired",
            extra={
                "task_id": task_id,
                "total_active_locks": len(_task_locks),
            }
        )
    
    # ✅ Periodic cleanup runs here (outside lock to avoid blocking)
    if should_cleanup:
        await cleanup_stale_locks(force=True)
    
    return True


async def release_task_lock(task_id: str):
    """
    Release lock and cleanup registry entry.
    
    ⚠️ ALWAYS call this in finally block to prevent lock leaks.
    
    Args:
        task_id: ClickUp task ID
    """
    async with _locks_registry_lock:
        if task_id in _task_locks:
            try:
                lock, timestamp = _task_locks[task_id]
                
                # Release lock if held
                if lock.locked():
                    lock.release()
                
                # Remove from registry
                del _task_locks[task_id]
                
                age_seconds = time.time() - timestamp
                
                logger.info(
                    "Task lock released",
                    extra={
                        "task_id": task_id,
                        "lock_duration_seconds": age_seconds,
                        "remaining_locks": len(_task_locks),
                    }
                )
            except Exception as e:
                logger.error(
                    f"Error releasing lock for {task_id}: {e}",
                    extra={
                        "task_id": task_id,
                        "error": str(e),
                    }
                )
        else:
            logger.warning(
                f"Attempted to release non-existent lock for {task_id}",
                extra={"task_id": task_id}
            )


async def get_lock_stats() -> dict:
    """
    Get statistics about current locks (for monitoring).
    
    Returns:
        Dict with lock statistics
    """
    async with _locks_registry_lock:
        now = time.time()
        
        ages = [now - ts for _, ts in _task_locks.values()]
        
        return {
            "total_locks": len(_task_locks),
            "oldest_lock_seconds": max(ages) if ages else 0,
            "newest_lock_seconds": min(ages) if ages else 0,
            "average_lock_age_seconds": sum(ages) / len(ages) if ages else 0,
            "stale_locks": sum(1 for age in ages if age > LOCK_TTL_SECONDS),
        }


# ============================================================================
# SIGNATURE VERIFICATION
# ============================================================================

def verify_signature(payload_body: bytes, signature: str, secret: str) -> bool:
    """
    Verify ClickUp webhook signature.
    
    Args:
        payload_body: Raw request body bytes
        signature: X-Signature header from ClickUp
        secret: Webhook secret from config
        
    Returns:
        True if signature is valid
    """
    if not signature:
        return False
    
    # Compute expected signature
    expected = hmac.new(
        secret.encode(),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected)


# ============================================================================
# DEPENDENCIES
# ============================================================================

async def get_orchestrator(request: Request):
    """Dependency to get active orchestrator from app state."""
    return request.app.state.orchestrator  # 🎯 Uses feature flag


async def get_clickup_client(request: Request):
    """Dependency to get ClickUp client from app state."""
    return request.app.state.clickup


# ============================================================================
# WEBHOOK ENDPOINT
# ============================================================================

@router.post("/clickup", response_model=WebhookResponse)
async def clickup_webhook(
    request: Request,
    orchestrator=Depends(get_orchestrator),
    clickup=Depends(get_clickup_client),
):
    """
    Handle ClickUp webhook events with synchronous processing.
    
    ⚠️ IMPORTANT: Processing happens synchronously (blocks until complete).
    This ensures no task loss on Railway restarts/deployments.
    
    Processing time: ~35-45 seconds
    ClickUp webhook timeout: 30 seconds for initial response
    
    Strategy: We return quick acknowledgment but continue processing.
    ClickUp will see eventual task status update via API.
    
    Ensures only ONE processing flow runs per task_id at any time.
    Duplicate webhooks are rejected immediately.
    """
    # Get signature and payload
    signature = request.headers.get("X-Signature", "")
    payload_body = await request.body()
    
    # Verify signature
    config = get_config()
    if not verify_signature(payload_body, signature, config.clickup_webhook_secret):
        logger.warning(
            "Invalid webhook signature",
            extra={"signature": signature[:10] + "..."}
        )
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse payload
    try:
        data = await request.json()
        
        # Extract basic info
        event = data.get("event")
        task_id = data.get("task_id")
        
        if not task_id:
            raise HTTPException(status_code=400, detail="Missing task_id")
        
        # Only process taskUpdated events
        if event != "taskUpdated":
            logger.info(
                f"Ignoring event: {event}",
                extra={"event": event, "task_id": task_id}
            )
            return {"status": "ignored", "reason": f"Event type {event} not supported"}
        
        # ====================================================================
        # 🔐 CRITICAL: ACQUIRE TASK LOCK
        # ====================================================================
        if not await acquire_task_lock(task_id):
            # Task already processing - reject duplicate webhook
            logger.warning(
                "Duplicate webhook rejected - task already processing",
                extra={"task_id": task_id, "event": event}
            )
            return {
                "status": "already_processing",
                "task_id": task_id,
                "message": "Task is already being processed"
            }
        
        # Lock acquired - proceed with validation
        # ====================================================================
        
        # Fetch full task data from ClickUp API
        logger.info(
            "Fetching full task data from ClickUp",
            extra={"task_id": task_id}
        )
        
        task_data = await clickup.get_task(task_id)
        # 🛡️ CHECK IF ALREADY COMPLETE
        task_status = task_data.get("status", {}).get("status", "").lower()
        if task_status == "complete":
            await release_task_lock(task_id)
            logger.info(
                "Task already complete, skipping",
                extra={"task_id": task_id, "status": task_status}
            )
            return {"status": "ignored", "reason": "Task already complete"}
        
        description = task_data.get("description", "") or task_data.get("text_content", "")
        attachments = task_data.get("attachments", [])
        
        # Validate task data
        if not description:
            await release_task_lock(task_id)  # Release before returning
            logger.warning(
                "No description in task",
                extra={"task_id": task_id}
            )
            return {"status": "ignored", "reason": "No description found"}
        
        # Check custom field (AI Edit checkbox)
        custom_fields = task_data.get("custom_fields", [])
        needs_ai_edit = False
        
        # config already loaded at top of function (line 329)
        for field in custom_fields:
            if field.get("id") == config.clickup_custom_field_id_ai_edit:
                if field.get("value") == "true" or field.get("value") is True:
                    needs_ai_edit = True
                    break

        if not needs_ai_edit:
            await release_task_lock(task_id)  # Release before returning
            logger.warning(
                "Custom field not checked",
                extra={"task_id": task_id}
            )
            return {"status": "ignored", "reason": "AI Edit checkbox not checked"}
        
        if not attachments:
            await release_task_lock(task_id)  # Release before returning
            logger.warning(
                "No attachments in task",
                extra={"task_id": task_id}
            )
            return {"status": "ignored", "reason": "No image attached"}
        
        # Get attachment URL
        attachment = attachments[0]
        attachment_url = attachment.get("url")

        if not attachment_url:
            await release_task_lock(task_id)  # Release before returning
            logger.warning(
                "No URL in attachment",
                extra={"task_id": task_id, "attachment": attachment}
            )
            return {"status": "ignored", "reason": "No attachment URL"}
        
        logger.info(
            "Webhook validated, starting SYNCHRONOUS processing",
            extra={
                "task_id": task_id,
                "event": event,
                "attachment_url": attachment_url,
                "description_length": len(description),
            }
        )
        
        # ====================================================================
        # ✅ NEW: SYNCHRONOUS PROCESSING (blocks until complete)
        # ====================================================================
        try:
            await process_edit_request(
                task_id=task_id,
                prompt=description,
                attachment_url=attachment_url,
                attachment_filename=attachment.get("title") or attachment.get("name") or "image.jpg",
                attachment_id=attachment.get("id"),
                orchestrator=orchestrator,
                clickup=clickup,
            )
            
            logger.info(
                "Processing completed successfully",
                extra={"task_id": task_id}
            )
            
            return {
                "status": "completed",
                "task_id": task_id,
            }
            
        except Exception as e:
            logger.error(
                f"Processing failed: {e}",
                extra={
                    "task_id": task_id,
                    "error": str(e),
                },
                exc_info=True
            )
            
            # Task will be marked as blocked in process_edit_request's exception handler
            return {
                "status": "failed",
                "task_id": task_id,
                "error": str(e),
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Webhook processing error: {e}",
            extra={"error": str(e)}
        )
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")


# ============================================================================
# BACKGROUND PROCESSING
# ============================================================================

async def process_edit_request(
    task_id: str,
    prompt: str,
    attachment_url: str,
    attachment_filename: str,
    attachment_id: str,
    orchestrator,
    clickup,
):
    """
    Background task to process edit request.
    
    This runs with task_id lock held from webhook handler.
    Lock is released in finally block to guarantee cleanup.
    
    Args:
        task_id: ClickUp task ID
        prompt: Edit instructions from task description
        attachment_url: URL of original image
        attachment_filename: Original filename (for format detection)
        attachment_id: Original attachment ID (to delete after conversion)
        orchestrator: Orchestrator instance
        clickup: ClickUp client instance
    """
    try:
        logger.info(
            f"Background processing started for task {task_id}",
            extra={
                "task_id": task_id,
                "prompt_length": len(prompt),
            }
        )
        
        # Use ClickUp attachment URL directly
        # Download original image from ClickUp
        logger.info("Downloading original image", extra={"task_id": task_id})
        original_bytes = await clickup.download_attachment(attachment_url)
        
        # Extract filename from attachment (from webhook payload closure)
        # Note: attachment variable is available from webhook handler scope
        filename = attachment_filename 
        
        logger.info(
            "Image downloaded",
            extra={
                "task_id": task_id,
                "file_name": filename,
                "size_kb": len(original_bytes) / 1024,
            }
        )
        
        # Convert to PNG (handles all formats)
        # ✅ NEW: Run in threadpool to avoid blocking event loop
        from fastapi.concurrency import run_in_threadpool
        
        converter = ImageConverter()
        
        try:
            png_bytes, png_filename = await run_in_threadpool(
                converter.convert_to_png,
                file_bytes=original_bytes,
                filename=filename
            )
            
            logger.info(
                "Format conversion successful",
                extra={
                    "task_id": task_id,
                    "original_format": filename.split('.')[-1],
                    "png_size_kb": len(png_bytes) / 1024,
                }
            )
            
        except UnsupportedFormatError as e:
            # User error - unsupported format
            logger.error(
                f"Unsupported format: {e}",
                extra={"task_id": task_id, "file_name": filename}
            )
            
            config = get_config()
            await clickup.update_task_status(
                task_id=task_id,
                status=config.clickup_status_blocked,
                comment=(
                    f"❌ **Unsupported File Format**\n\n"
                    f"File: {filename}\n"
                    f"Error: {str(e)}\n\n"
                    f"✅ Please export as:\n"
                    f"• JPEG/JPG (best for photos)\n"
                    f"• PNG (best for logos/transparency)\n"
                    f"• PDF (for print-ready files)\n"
                    f"• PSD (Photoshop files)\n\n"
                    f"Then re-upload and check AI Edit again."
                )
            )
            return  # Exit background task
            
        except ImageConversionError as e:
            # Conversion failed - file corrupted or invalid
            logger.error(
                f"Conversion failed: {e}",
                extra={"task_id": task_id, "file_name": filename}
            )
            
            config = get_config()
            await clickup.update_task_status(
                task_id=task_id,
                status=config.clickup_status_blocked,
                comment=(
                    f"❌ **File Conversion Error**\n\n"
                    f"File: {filename}\n"
                    f"Error: {str(e)}\n\n"
                    f"The file may be corrupted or invalid. "
                    f"Please check the file and try again."
                )
            )
            return  # Exit background task
        
        # Upload converted PNG to ClickUp
        logger.info("Uploading converted PNG to ClickUp", extra={"task_id": task_id})
        await clickup.upload_attachment(
            task_id=task_id,
            image_bytes=png_bytes,
            filename=png_filename
        )

        logger.info(
            "PNG uploaded, fetching task to get URL",
            extra={"task_id": task_id}
        )

        # Fetch task to get the new PNG attachment URL
        task_data = await clickup.get_task(task_id)
        attachments = task_data.get("attachments", [])

        # Find the PNG we just uploaded (it's the last one)
        png_attachment = attachments[-1] if attachments else None
        original_url = png_attachment.get("url") if png_attachment else None

        if not original_url:
            raise Exception("Failed to get PNG URL after upload")

        logger.info(
            "PNG URL retrieved, deleting original attachment",
            extra={"task_id": task_id, "png_url": original_url}
        )
        
        # Process with iterations (ENTIRE WORKFLOW)
        logger.info("Starting orchestration", extra={"task_id": task_id})
        
        # Process with old orchestrator
        result = await orchestrator.process_with_iterations(
            task_id=task_id,
            prompt=prompt,
            original_image_url=original_url,
            original_image_bytes=png_bytes
        )
        
        # Handle result
        if result.status == "success":
            # Upload edited image to ClickUp
            logger.info("Uploading result to ClickUp", extra={"task_id": task_id})
            await clickup.upload_attachment(
                task_id=task_id,
                image_bytes=result.final_image.image_bytes,
                filename=f"edited_{task_id}.png",
            )

            # 🔧 UNCHECK AI EDIT CHECKBOX
            logger.info("Unchecking AI Edit checkbox", extra={"task_id": task_id})
            config = get_config()
            await clickup.update_custom_field(
                task_id=task_id,
                field_id=config.clickup_custom_field_id_ai_edit,
                value=False,
            )
            
            # Update task status
            comment = (
                f"✅ **Edit completed successfully!**\n\n"
                f"**Model Used:** {result.model_used}\n"
                f"**Iterations:** {result.iterations}\n"
                f"**Processing Time:** {result.processing_time_seconds:.1f}s\n\n"
                f"The edited image has been attached to this task."
            )
            
            await clickup.update_task_status(
                task_id=task_id,
                status=config.clickup_status_complete,
                comment=comment,
            )
            
            logger.info(
                "Task completed successfully",
                extra={
                    "task_id": task_id,
                    "model": result.model_used,
                    "iterations": result.iterations,
                    "processing_time": result.processing_time_seconds,
                }
            )
            
        else:
            # Hybrid fallback already triggered in orchestrator
            logger.info(
                "Task requires human review",
                extra={
                    "task_id": task_id,
                    "status": result.status,
                }
            )
        
    except Exception as e:
        logger.error(
            f"Task {task_id} failed: {e}",
            extra={
                "task_id": task_id,
                "error": str(e),
            },
            exc_info=True  # Include full traceback
        )
        
        try:
            # Attempt to update ClickUp with error
            config = get_config()
            await clickup.update_task_status(
                task_id=task_id,
                status=config.clickup_status_blocked,
                comment=f"❌ **Processing Error**\n\nError: {str(e)}\n\nPlease contact support or retry manually.",
            )
        except Exception as notify_error:
            # If even error notification fails, just log it
            logger.error(
                f"Failed to notify ClickUp of error for task {task_id}",
                extra={"task_id": task_id, "notify_error": str(notify_error)}
            )
    
    finally:
        # ====================================================================
        # 🔐 CRITICAL: ALWAYS RELEASE LOCK
        # ====================================================================
        await release_task_lock(task_id)
        logger.info(
            "Background processing complete, lock released",
            extra={"task_id": task_id}
        )