"""ClickUp webhook handler with per-task locking."""

import hmac
import hashlib
import asyncio
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from typing import Dict, Any

from ..models.schemas import WebhookPayload, ClickUpTask, ClickUpAttachment
from ..utils.logger import get_logger
from ..utils.config import get_config
from ..utils.image_converter import ImageConverter
from ..utils.errors import UnsupportedFormatError, ImageConversionError

logger = get_logger(__name__)

router = APIRouter()

# ============================================================================
# 🔐 TASK-LEVEL LOCKING SYSTEM
# ============================================================================

# Global registry of locks per task_id
_task_locks: dict[str, asyncio.Lock] = {}
_locks_registry_lock = asyncio.Lock()  # Protects the registry itself


async def acquire_task_lock(task_id: str) -> bool:
    """
    Try to acquire exclusive lock for a task_id.
    
    Returns:
        True if lock acquired (task can proceed)
        False if already locked (task already processing)
    """
    async with _locks_registry_lock:
        # Check if task already has a lock (means it's processing)
        if task_id in _task_locks:
            # Lock exists = task already processing
            logger.info(
                "Task already processing, rejecting duplicate",
                extra={"task_id": task_id}
            )
            return False
        
        # Create new lock for this task
        _task_locks[task_id] = asyncio.Lock()
        await _task_locks[task_id].acquire()
        
        logger.info(
            "Task lock acquired",
            extra={"task_id": task_id}
        )
        return True


async def release_task_lock(task_id: str):
    """
    Release lock and cleanup registry entry.
    
    ALWAYS call this in finally block to prevent lock leaks.
    """
    async with _locks_registry_lock:
        if task_id in _task_locks:
            _task_locks[task_id].release()
            del _task_locks[task_id]
            
            logger.info(
                "Task lock released",
                extra={"task_id": task_id}
            )


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

@router.post("/clickup")
async def clickup_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    orchestrator=Depends(get_orchestrator),
    clickup=Depends(get_clickup_client),
):
    """
    Handle ClickUp webhook events with per-task locking.
    
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

        for field in custom_fields:
            if field.get("id") == "b2c19afd-0ef2-485c-94b9-3a6124374ff4":
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
            "Webhook validated, queuing background processing",
            extra={
                "task_id": task_id,
                "event": event,
                "attachment_url": attachment_url,
                "description_length": len(description),
            }
        )
        
        # ====================================================================
        # Queue processing in background (lock will be held until completion)
        # ====================================================================
        background_tasks.add_task(
            process_edit_request,
            task_id=task_id,
            prompt=description,
            attachment_url=attachment_url,
            attachment_filename=attachment.get("title") or attachment.get("name") or "image.jpg",
            attachment_id=attachment.get("id"),
            orchestrator=orchestrator,
            clickup=clickup,
        )
        
        return {
            "status": "queued",
            "task_id": task_id,
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
        converter = ImageConverter()
        
        try:
            png_bytes, png_filename = await converter.convert_to_png(
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
            
            await clickup.update_task_status(
                task_id=task_id,
                status="blocked",
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
            
            await clickup.update_task_status(
                task_id=task_id,
                status="blocked",
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
            await clickup.update_custom_field(
                task_id=task_id,
                field_id="b2c19afd-0ef2-485c-94b9-3a6124374ff4",
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
                status="Complete",
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
            await clickup.update_task_status(
                task_id=task_id,
                status="blocked",
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