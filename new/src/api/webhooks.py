"""ClickUp webhook handler with per-task locking."""

import hmac
import hashlib
import asyncio
import time
from typing import Dict, Any, Tuple, Optional, List
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel

from ..models.schemas import WebhookPayload, ClickUpTask, ClickUpAttachment, ClassifiedTask
from ..utils.logger import get_logger
from ..utils.config import get_config
from ..utils.image_converter import ImageConverter
from ..utils.errors import UnsupportedFormatError, ImageConversionError
from ..core.classifier import Classifier
from ..core.brand_analyzer import BrandAnalyzer
from ..models.enums import TaskType, AttachmentIntent

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


async def get_classifier(request: Request):
    """Dependency to get classifier from app state."""
    return request.app.state.classifier


async def get_brand_analyzer(request: Request):
    """Dependency to get brand analyzer from app state."""
    return request.app.state.brand_analyzer


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
        
        # ✅ Only process tasks in "to do" status
        if task_status not in ["to do", "todo"]:
            await release_task_lock(task_id)
            logger.info(
                f"Task not in 'to do' status, skipping",
                extra={"task_id": task_id, "status": task_status}
            )
            return {"status": "ignored", "reason": f"Task status is '{task_status}', not 'to do'"}
        
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
        
        # Build attachments list for V2.0
        attachments_data = []
        for att in attachments:
            att_url = att.get("url")
            if att_url:
                attachments_data.append({
                    "url": att_url,
                    "filename": att.get("title") or att.get("name") or "image.jpg",
                    "id": att.get("id"),
                })
        
        if not attachments_data:
            await release_task_lock(task_id)  # Release before returning
            logger.warning(
                "No valid attachment URLs",
                extra={"task_id": task_id}
            )
            return {"status": "ignored", "reason": "No attachment URL"}
        
        logger.info(
            "Webhook validated, starting SYNCHRONOUS processing",
            extra={
                "task_id": task_id,
                "event": event,
                "attachment_count": len(attachments_data),
                "description_length": len(description),
            }
        )
        
        # ====================================================================
        # ✅ V2.0: SYNCHRONOUS PROCESSING WITH CLASSIFICATION
        # ====================================================================
        try:
            # Get classifier and brand analyzer
            classifier = await get_classifier(request)
            brand_analyzer = await get_brand_analyzer(request)
            
            await process_edit_request(
                task_id=task_id,
                prompt=description,
                attachments_data=attachments_data,
                orchestrator=orchestrator,
                clickup=clickup,
                classifier=classifier,
                brand_analyzer=brand_analyzer,
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
    attachments_data: List[dict],  # CHANGED: List of {url, filename, id}
    orchestrator,
    clickup,
    classifier: Classifier,
    brand_analyzer: BrandAnalyzer,
):
    """
    Background task to process edit request.
    
    V2.0: Supports multiple attachments and task classification.
    """
    try:
        # ✅ FIRST THING: Change status to "in progress"
        await clickup.update_task_status(task_id, "in progress")
        logger.info("Status set to 'in progress'", extra={"task_id": task_id})
        
        logger.info(
            f"Background processing started for task {task_id}",
            extra={
                "task_id": task_id,
                "attachment_count": len(attachments_data),
            }
        )
        
        # ================================================================
        # PHASE 1: DOWNLOAD ALL ATTACHMENTS
        # ================================================================
        downloaded_attachments = []  # [(filename, png_bytes), ...]
        attachment_urls = {}  # {index: url} for later use
        
        converter = ImageConverter()
        
        for i, att_data in enumerate(attachments_data):
            attachment_url = att_data.get("url")
            filename = att_data.get("filename", f"image_{i}.jpg")
            
            logger.info(
                f"Downloading attachment {i + 1}/{len(attachments_data)}",
                extra={"task_id": task_id, "file_name": filename}
            )
            
            try:
                # Download
                original_bytes = await clickup.download_attachment(attachment_url)
                
                # Convert to PNG (async)
                png_bytes, png_filename = await converter.convert_to_png(
                    file_bytes=original_bytes,
                    filename=filename
                )
                
                downloaded_attachments.append((png_filename, png_bytes))
                
                # Upload PNG to ClickUp to get URL for WaveSpeed
                await clickup.upload_attachment(
                    task_id=task_id,
                    image_bytes=png_bytes,
                    filename=png_filename
                )
                
                # Get the uploaded URL
                task_data = await clickup.get_task(task_id)
                current_attachments = task_data.get("attachments", [])
                if current_attachments:
                    # Latest uploaded is last
                    attachment_urls[i] = current_attachments[-1].get("url")
                
                logger.info(
                    f"Attachment {i + 1} processed",
                    extra={
                        "task_id": task_id,
                        "file_name": png_filename,
                        "size_kb": len(png_bytes) / 1024,
                    }
                )
                
            except (UnsupportedFormatError, ImageConversionError) as e:
                logger.error(
                    f"Attachment {i + 1} failed: {e}",
                    extra={"task_id": task_id, "file_name": filename}
                )
                # Continue with other attachments
                continue
        
        if not downloaded_attachments:
            await clickup.update_task_status(
                task_id=task_id,
                status="blocked",
                comment="❌ **No valid images found**\n\nCould not process any attachments."
            )
            return
        
        # ================================================================
        # PHASE 2: CLASSIFY TASK
        # ================================================================
        logger.info("Starting classification", extra={"task_id": task_id})
        
        classified = await classifier.classify(
            description=prompt,
            attachments=downloaded_attachments,
        )
        
        logger.info(
            "Classification complete",
            extra={
                "task_id": task_id,
                "task_type": classified.task_type.value,
                "dimensions": classified.dimensions,
            }
        )
        
        # ================================================================
        # PHASE 3: BRAND ANALYSIS (if website detected)
        # ================================================================
        if classified.website_url:
            logger.info(
                "Starting brand analysis",
                extra={"task_id": task_id, "website": classified.website_url}
            )
            
            brand_result = await brand_analyzer.analyze(classified.website_url)
            
            if brand_result:
                classified.brand_aesthetic = brand_result.get("brand_aesthetic")
                logger.info(
                    "Brand analysis complete",
                    extra={"task_id": task_id}
                )
        
        # ================================================================
        # PHASE 4: ROUTE AND EXECUTE
        # ================================================================
        
        if classified.task_type == TaskType.SIMPLE_EDIT:
            # ============================================================
            # SIMPLE_EDIT: Use existing flow (unchanged)
            # ============================================================
            logger.info("Routing to SIMPLE_EDIT flow", extra={"task_id": task_id})
            
            # Get first include_in_output attachment
            main_attachment = None
            main_url = None
            main_bytes = None
            
            for att in classified.attachments:
                if att.intent == AttachmentIntent.INCLUDE_IN_OUTPUT:
                    idx = att.index
                    main_url = attachment_urls.get(idx)
                    main_bytes = downloaded_attachments[idx][1] if idx < len(downloaded_attachments) else None
                    break
            
            if not main_url or not main_bytes:
                # Fallback to first attachment
                main_url = attachment_urls.get(0)
                main_bytes = downloaded_attachments[0][1]
            
            # Call existing flow
            result = await orchestrator.process_with_iterations(
                task_id=task_id,
                prompt=prompt,
                original_image_url=main_url,
                original_image_bytes=main_bytes,
                task_type="SIMPLE_EDIT",
            )
            
            # Handle result (existing logic)
            await _handle_simple_edit_result(result, task_id, clickup)
            
        else:
            # ============================================================
            # BRANDED_CREATIVE: New flow with dimension loop
            # ============================================================
            logger.info(
                "Routing to BRANDED_CREATIVE flow",
                extra={
                    "task_id": task_id,
                    "dimensions": classified.dimensions,
                }
            )
            
            await _process_branded_creative(
                task_id=task_id,
                classified=classified,
                downloaded_attachments=downloaded_attachments,
                attachment_urls=attachment_urls,
                orchestrator=orchestrator,
                clickup=clickup,
            )
        
    except Exception as e:
        logger.error(
            f"Task {task_id} failed: {e}",
            extra={"task_id": task_id, "error": str(e)},
            exc_info=True
        )
        
        try:
            await clickup.update_task_status(
                task_id=task_id,
                status="blocked",
                comment=f"❌ **Processing Error**\n\nError: {str(e)}\n\nPlease contact support.",
            )
        except Exception as notify_error:
            logger.error(f"Failed to notify ClickUp: {notify_error}")
    
    finally:
        # ✅ ALWAYS uncheck checkbox (prevents re-trigger)
        try:
            config = get_config()
            await clickup.update_custom_field(
                task_id=task_id,
                field_id=config.clickup_custom_field_id_ai_edit,
                value=False,
            )
            logger.info("Checkbox unchecked", extra={"task_id": task_id})
        except Exception as e:
            logger.error(f"Failed to uncheck checkbox: {e}")
        
        await release_task_lock(task_id)
        logger.info("Background processing complete", extra={"task_id": task_id})


async def _handle_simple_edit_result(result, task_id: str, clickup):
    """Handle result from SIMPLE_EDIT flow."""
    config = get_config()
    
    if result.status == "success":
        await clickup.upload_attachment(
            task_id=task_id,
            image_bytes=result.final_image.image_bytes,
            filename=f"edited_{task_id}.png",
        )
        
        # ✅ Checkbox uncheck moved to finally block in process_edit_request
        
        comment = (
            f"✅ **Edit completed!**\n\n"
            f"**Model:** {result.model_used}\n"
            f"**Iterations:** {result.iterations}\n"
            f"**Time:** {result.processing_time_seconds:.1f}s"
        )
        
        await clickup.update_task_status(
            task_id=task_id,
            status=config.clickup_status_complete,
            comment=comment,
        )
    else:
        logger.info(
            "Task requires human review",
            extra={"task_id": task_id, "status": result.status}
        )


async def _process_branded_creative(
    task_id: str,
    classified: ClassifiedTask,
    downloaded_attachments: List[tuple],
    attachment_urls: dict,
    orchestrator,
    clickup,
):
    """
    Process BRANDED_CREATIVE task with dimension loop.
    
    Each dimension uses existing orchestrator flow.
    Subsequent dimensions use previous result as base.
    """
    config = get_config()
    results = []
    
    # Get include_in_output images
    include_urls = []
    include_bytes = []
    
    for att in classified.attachments:
        if att.intent == AttachmentIntent.INCLUDE_IN_OUTPUT:
            idx = att.index
            if idx in attachment_urls:
                include_urls.append(attachment_urls[idx])
            if idx < len(downloaded_attachments):
                include_bytes.append(downloaded_attachments[idx][1])
    
    if not include_urls:
        await clickup.update_task_status(
            task_id=task_id,
            status="blocked",
            comment="❌ **No images to include**\n\nNo attachments marked for output."
        )
        return
    
    # Loop through dimensions
    for i, dimension in enumerate(classified.dimensions):
        logger.info(
            f"Processing dimension {i + 1}/{len(classified.dimensions)}: {dimension}",
            extra={"task_id": task_id, "dimension": dimension}
        )
        
        try:
            if i == 0:
                # First dimension: use original attachments
                # Build rich prompt with all context
                prompt = _build_branded_prompt(classified, dimension)
                image_url = include_urls[0]  # Primary image
                image_bytes = include_bytes[0]
                additional_urls = include_urls[1:] if len(include_urls) > 1 else None  # ✅ Additional image URLs
                additional_bytes = include_bytes[1:] if len(include_bytes) > 1 else None  # ✅ Additional image bytes
            else:
                # Subsequent dimensions: adapt from previous result
                prompt = _build_adapt_prompt(classified, dimension)
                image_url = results[-1].final_image.temp_url
                image_bytes = results[-1].final_image.image_bytes
                additional_urls = None  # No additional images for adaptations
                additional_bytes = None
            
            # Use existing orchestrator flow
            result = await orchestrator.process_with_iterations(
                task_id=task_id,
                prompt=prompt,
                original_image_url=image_url,
                original_image_bytes=image_bytes,
                task_type="BRANDED_CREATIVE",
                additional_image_urls=additional_urls,  # ✅ Pass additional image URLs
                additional_image_bytes=additional_bytes,  # ✅ Pass additional image bytes
            )
            
            if result.status == "success":
                results.append(result)
                logger.info(
                    f"Dimension {dimension} complete",
                    extra={"task_id": task_id, "score": result.final_image}
                )
            else:
                logger.warning(
                    f"Dimension {dimension} failed",
                    extra={"task_id": task_id}
                )
                # Continue with other dimensions
        
        except Exception as e:
            logger.error(
                f"Dimension {dimension} error: {e}",
                extra={"task_id": task_id, "dimension": dimension}
            )
            # Continue with other dimensions
    
    # Upload results
    if results:
        for i, result in enumerate(results):
            dimension = classified.dimensions[i]
            dim_label = dimension.replace(":", "x")
            
            await clickup.upload_attachment(
                task_id=task_id,
                image_bytes=result.final_image.image_bytes,
                filename=f"edited_{task_id}_{dim_label}.png",
            )
        
        # ✅ Checkbox uncheck moved to finally block in process_edit_request
        
        dims_done = [classified.dimensions[i] for i in range(len(results))]
        dims_failed = [d for d in classified.dimensions if d not in dims_done]
        
        status_msg = f"✅ **Creative completed!**\n\n"
        status_msg += f"**Dimensions:** {', '.join(dims_done)}\n"
        
        if dims_failed:
            status_msg += f"**Failed:** {', '.join(dims_failed)}\n"
        
        status_msg += f"**Model:** {results[0].model_used}"
        
        await clickup.update_task_status(
            task_id=task_id,
            status=config.clickup_status_complete,
            comment=status_msg,
        )
    else:
        await clickup.update_task_status(
            task_id=task_id,
            status="blocked",  # Use actual ClickUp status
            comment="❌ **All dimensions failed**\n\nNo successful outputs generated."
        )


def _build_branded_prompt(classified: ClassifiedTask, dimension: str) -> str:
    """Build rich prompt for first dimension."""
    parts = []
    
    # Dimension
    parts.append(f"Create a {dimension} marketing graphic.")
    
    # Text elements
    if classified.text_elements:
        parts.append("\nText content:")
        for te in classified.text_elements:
            hint = f" ({te.style_hint})" if te.style_hint else ""
            parts.append(f"- {te.role}: \"{te.content}\"{hint}")
    
    # Style
    if classified.style_hints:
        aesthetic = classified.style_hints.get("aesthetic")
        if aesthetic:
            parts.append(f"\nStyle: {aesthetic}")
    
    # Typography
    if classified.typography:
        parts.append(f"Typography: {classified.typography}")
    
    # Colors
    if classified.color_scheme:
        colors = ", ".join(f"{k}: {v}" for k, v in classified.color_scheme.items())
        parts.append(f"Colors: {colors}")
    
    # Brand aesthetic
    if classified.brand_aesthetic:
        ba = classified.brand_aesthetic
        if isinstance(ba, dict):
            prompt_guidance = ba.get("prompt_guidance")
            if prompt_guidance:
                parts.append(f"\nBrand guidance: {prompt_guidance}")
    
    # Layout from sketch
    for att in classified.attachments:
        if att.extracted_layout:
            parts.append(f"\nLayout (from sketch): {att.extracted_layout}")
    
    # Style from inspiration
    for att in classified.attachments:
        if att.extracted_style:
            parts.append(f"\nStyle reference: {att.extracted_style}")
    
    # Image descriptions
    parts.append("\nImages provided:")
    for att in classified.attachments:
        if att.intent == AttachmentIntent.INCLUDE_IN_OUTPUT:
            parts.append(f"- {att.role}: {att.description or att.filename}")
    
    return "\n".join(parts)


def _build_adapt_prompt(classified: ClassifiedTask, dimension: str) -> str:
    """Build adaptation prompt for subsequent dimensions."""
    return f"""Adapt this image to {dimension} format.

Keep EXACTLY the same:
- All text content and hierarchy
- Logo placement (relative position)
- Color palette and style
- Overall mood and aesthetic

Only adjust composition for the new aspect ratio.
Maintain visual consistency with the original."""