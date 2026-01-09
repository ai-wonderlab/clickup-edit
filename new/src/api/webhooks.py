"""ClickUp webhook handler with per-task locking."""

import hmac
import hashlib
import asyncio
import time
import uuid
from typing import Dict, Any, Tuple, Optional, List
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel

from ..models.schemas import WebhookPayload, ClickUpTask, ClickUpAttachment, ClassifiedTask
from ..utils.logger import get_logger
from ..utils.config import get_config
from ..utils.image_converter import ImageConverter
from ..utils.images import get_closest_aspect_ratio
from ..utils.errors import UnsupportedFormatError, ImageConversionError
from ..core.brand_analyzer import BrandAnalyzer
from ..core.task_parser import TaskParser, ParsedTask
from ..models.enums import TaskType

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
            "🔐 LOCK ACQUIRED",
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
                    "🔓 LOCK RELEASED",
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


async def get_brand_analyzer(request: Request):
    """Dependency to get brand analyzer from app state."""
    return request.app.state.brand_analyzer


async def get_task_parser(request: Request):
    """Dependency to get task parser from app state."""
    return request.app.state.task_parser


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
        
        # ====================================================================
        # 🔒 LOCK ACQUIRED - Everything below is in try/finally for safe release
        # ====================================================================
        run_id = str(uuid.uuid4())[:8]  # Short unique ID for this run
        
        try:
            logger.info(
                f"🚀 RUN START [{run_id}]",
                extra={"task_id": task_id, "run_id": run_id, "event": event}
            )
            
            # Fetch full task data from ClickUp API
            logger.info(
                "Fetching full task data from ClickUp",
                extra={"task_id": task_id, "run_id": run_id}
            )
            
            task_data = await clickup.get_task(task_id)
            
            # � TEMPORARY DEBUG: See raw ClickUp data
            logger.info(f"📝 RAW DESCRIPTION: {task_data.get('description', 'NO DESCRIPTION')}")
            logger.info(f"📝 RAW DESCRIPTION REPR: {repr(task_data.get('description', ''))}")
            
            # �🛡️ CHECK IF ALREADY COMPLETE
            task_status = task_data.get("status", {}).get("status", "").lower()
            if task_status == "complete":
                logger.info(
                    "Task already complete, skipping",
                    extra={"task_id": task_id, "run_id": run_id, "status": task_status}
                )
                return {"status": "ignored", "reason": "Task already complete"}
            
            # ✅ Only process tasks in "to do" status
            if task_status not in ["to do", "todo"]:
                logger.info(
                    f"Task not in 'to do' status, skipping",
                    extra={"task_id": task_id, "run_id": run_id, "status": task_status}
                )
                return {"status": "ignored", "reason": f"Task status is '{task_status}', not 'to do'"}
            
            # Check custom field (AI Edit checkbox)
            custom_fields = task_data.get("custom_fields", [])
            needs_ai_edit = False
            
            for field in custom_fields:
                if field.get("id") == config.clickup_custom_field_id_ai_edit:
                    if field.get("value") == "true" or field.get("value") is True:
                        needs_ai_edit = True
                        break

            if not needs_ai_edit:
                logger.warning(
                    "Custom field not checked",
                    extra={"task_id": task_id, "run_id": run_id}
                )
                return {"status": "ignored", "reason": "AI Edit checkbox not checked"}
            
            # ====================================================================
            # ✅ V3.0: PARSE TASK FROM CUSTOM FIELDS
            # ====================================================================
            task_parser = await get_task_parser(request)
            parsed = task_parser.parse(task_data)
            
            # Validate required fields based on task type
            if parsed.is_edit:
                if not parsed.main_image:
                    logger.warning(
                        "Edit task requires Main Image",
                        extra={"task_id": task_id, "run_id": run_id}
                    )
                    return {"status": "ignored", "reason": "Edit task requires Main Image"}
            elif parsed.is_creative:
                if not parsed.main_image:
                    logger.warning(
                        "Creative task requires Main Image",
                        extra={"task_id": task_id, "run_id": run_id}
                    )
                    return {"status": "ignored", "reason": "Creative task requires Main Image"}
                if not parsed.main_text:
                    logger.warning(
                        "Creative task requires Main Text",
                        extra={"task_id": task_id, "run_id": run_id}
                    )
                    return {"status": "ignored", "reason": "Creative task requires Main Text"}
            
            # Build prompt from parsed fields
            prompt = task_parser.build_prompt(parsed)
            
            logger.info(
                "Task parsed from custom fields",
                extra={
                    "task_id": task_id,
                    "run_id": run_id,
                    "task_type": parsed.task_type,
                    "dimensions": parsed.dimensions,
                    "has_reference": len(parsed.reference_images) > 0,
                }
            )
            
            # Build attachments list with roles
            attachments_data = []
            
            # Main images first
            for att in parsed.main_image:
                attachments_data.append({
                    "url": att.url,
                    "filename": att.filename,
                    "role": "main",
                })
            
            # Additional images second
            for att in parsed.additional_images:
                attachments_data.append({
                    "url": att.url,
                    "filename": att.filename,
                    "role": "additional",
                })
            
            # Logo third
            for att in parsed.logo:
                attachments_data.append({
                    "url": att.url,
                    "filename": att.filename,
                    "role": "logo",
                })
            
            # Reference images last (for context only)
            for att in parsed.reference_images:
                attachments_data.append({
                    "url": att.url,
                    "filename": att.filename,
                    "role": "reference",
                })
            
            logger.info(
                "Webhook validated, starting SYNCHRONOUS processing",
                extra={
                    "task_id": task_id,
                    "run_id": run_id,
                    "event": event,
                    "attachment_count": len(attachments_data),
                    "prompt_length": len(prompt),
                }
            )
            
            # ====================================================================
            # ✅ V3.0: SYNCHRONOUS PROCESSING WITH PARSED TASK
            # ====================================================================
            brand_analyzer = await get_brand_analyzer(request)
            
            await process_edit_request(
                task_id=task_id,
                prompt=prompt,
                attachments_data=attachments_data,
                parsed_task=parsed,
                orchestrator=orchestrator,
                clickup=clickup,
                brand_analyzer=brand_analyzer,
                run_id=run_id,
            )
            
            logger.info(
                f"🏁 RUN COMPLETE [{run_id}]",
                extra={"task_id": task_id, "run_id": run_id}
            )
            
            return {
                "status": "completed",
                "task_id": task_id,
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"❌ RUN FAILED [{run_id if 'run_id' in dir() else 'N/A'}]: {e}",
                extra={
                    "task_id": task_id,
                    "error": str(e),
                },
                exc_info=True
            )
            return {
                "status": "failed",
                "task_id": task_id,
                "error": str(e),
            }
        finally:
            # ====================================================================
            # 🔓 ALWAYS RELEASE LOCK - This is the ONLY place lock is released
            # ====================================================================
            await release_task_lock(task_id)
        
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
    attachments_data: List[dict],  # List of {url, filename, role}
    parsed_task: ParsedTask,
    orchestrator,
    clickup,
    brand_analyzer: BrandAnalyzer,
    run_id: str = "unknown",
):
    """
    Process edit request - simplified with parsed task data.
    
    Routing is based on parsed_task.task_type from custom fields.
    """
    try:
        # ✅ FIRST THING: Change status to "in progress"
        await clickup.update_task_status(task_id, "in progress")
        logger.info("Status set to 'in progress'", extra={"task_id": task_id, "run_id": run_id})
        
        logger.info(
            f"Background processing started for task {task_id}",
            extra={
                "task_id": task_id,
                "run_id": run_id,
                "task_type": parsed_task.task_type,
                "attachment_count": len(attachments_data),
            }
        )
        
        # ================================================================
        # PHASE 1: DOWNLOAD ATTACHMENTS BY ROLE
        # ================================================================
        main_images = []      # For generation: (filename, bytes, url)
        reference_images = [] # For context only: (filename, bytes, url)
        logo_images = []      # For overlay: (filename, bytes, url)
        
        converter = ImageConverter()
        
        logger.info(
            "Starting attachment download phase",
            extra={
                "task_id": task_id,
                "total_attachments": len(attachments_data),
                "attachment_roles": [a.get("role") for a in attachments_data],
            }
        )
        
        for i, att_data in enumerate(attachments_data):
            role = att_data.get("role", "main")
            url = att_data["url"]
            filename = att_data["filename"]
            
            logger.info(
                f"Downloading attachment {i + 1}/{len(attachments_data)}",
                extra={"task_id": task_id, "file_name": filename, "role": role}
            )
            
            try:
                # Download
                original_bytes = await clickup.download_attachment(url)
                
                # Convert to PNG (async)
                png_bytes, png_filename = await converter.convert_to_png(
                    file_bytes=original_bytes,
                    filename=filename
                )
                
                # Upload PNG to ClickUp and get URL directly from response
                upload_result = await clickup.upload_attachment(
                    task_id=task_id,
                    image_bytes=png_bytes,
                    filename=png_filename
                )
                uploaded_url = upload_result.get("url")
                
                if not uploaded_url:
                    logger.error(
                        f"Upload response missing URL for {filename}",
                        extra={"task_id": task_id, "index": i}
                    )
                    continue
                
                # Store by role
                if role == "main":
                    main_images.append((png_filename, png_bytes, uploaded_url))
                elif role == "additional":
                    main_images.append((png_filename, png_bytes, uploaded_url))  # Goes to generation
                elif role == "logo":
                    logo_images.append((png_filename, png_bytes, uploaded_url))
                    main_images.append((png_filename, png_bytes, uploaded_url))  # ALSO goes to generation!
                elif role == "reference":
                    reference_images.append((png_filename, png_bytes, uploaded_url))  # Context only
                
                logger.info(
                    f"Attachment {i + 1} processed",
                    extra={
                        "task_id": task_id,
                        "file_name": png_filename,
                        "role": role,
                        "size_kb": len(png_bytes) / 1024,
                    }
                )
                
            except (UnsupportedFormatError, ImageConversionError) as e:
                logger.error(
                    f"Attachment {i + 1} failed: {e}",
                    extra={"task_id": task_id, "file_name": filename}
                )
                continue
        
        logger.info(
            "PHASE 1 COMPLETE - Attachment summary",
            extra={
                "task_id": task_id,
                "main_count": len(main_images),
                "reference_count": len(reference_images),
                "logo_count": len(logo_images),
            }
        )
        
        if not main_images:
            await clickup.update_task_status(
                task_id=task_id,
                status="blocked",
                comment="❌ **No valid images found**\n\nCould not process any main images."
            )
            return
        
        # ================================================================
        # PHASE 2: BRAND ANALYSIS (if website provided)
        # ================================================================
        brand_aesthetic = None
        if parsed_task.brand_website:
            logger.info(
                "Starting brand analysis",
                extra={"task_id": task_id, "website": parsed_task.brand_website[:80]}
            )
            
            brand_result = await brand_analyzer.analyze(parsed_task.brand_website)
            if brand_result:
                brand_aesthetic = brand_result.get("brand_aesthetic")
                logger.info("Brand analysis complete", extra={"task_id": task_id})
        
        # ================================================================
        # PHASE 3: ROUTE BY TASK TYPE
        # ================================================================
        
        if parsed_task.is_edit:
            # ============================================================
            # SIMPLE EDIT FLOW
            # ============================================================
            logger.info("Routing to SIMPLE_EDIT flow", extra={"task_id": task_id})
            
            main_url = main_images[0][2] if main_images else None
            main_bytes = main_images[0][1] if main_images else None
            
            if not main_url or not main_bytes:
                await clickup.update_task_status(
                    task_id=task_id,
                    status="blocked",
                    comment="❌ **No image available**\n\nCould not find image to edit."
                )
                return
            
            result = await orchestrator.process_with_iterations(
                task_id=task_id,
                prompt=prompt,
                original_image_url=main_url,
                original_image_bytes=main_bytes,
                task_type="SIMPLE_EDIT",
            )
            
            await _handle_simple_edit_result(result, task_id, clickup)
            
        else:
            # ============================================================
            # BRANDED CREATIVE FLOW
            # ============================================================
            logger.info(
                "Routing to BRANDED_CREATIVE flow",
                extra={
                    "task_id": task_id,
                    "dimensions": parsed_task.dimensions,
                }
            )
            
            dimensions = parsed_task.dimensions or ["1:1"]
            
            # Prepare image lists
            generation_urls = [img[2] for img in main_images]
            generation_bytes = [img[1] for img in main_images]
            context_bytes = [img[1] for img in main_images + reference_images]
            
            await _process_branded_creative_v2(
                task_id=task_id,
                parsed_task=parsed_task,
                prompt=prompt,
                dimensions=dimensions,
                generation_urls=generation_urls,
                generation_bytes=generation_bytes,
                context_bytes=context_bytes,
                logo_bytes=logo_images[0][1] if logo_images else None,
                brand_aesthetic=brand_aesthetic,
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
            logger.info("Checkbox unchecked", extra={"task_id": task_id, "run_id": run_id})
        except Exception as e:
            logger.error(f"Failed to uncheck checkbox: {e}")
        
        # ⚠️ NOTE: Lock release is now handled in the webhook handler's finally block
        logger.info("process_edit_request complete", extra={"task_id": task_id, "run_id": run_id})


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


async def _process_branded_creative_v2(
    task_id: str,
    parsed_task: ParsedTask,
    prompt: str,
    dimensions: List[str],
    generation_urls: List[str],
    generation_bytes: List[bytes],
    context_bytes: List[bytes],
    logo_bytes: Optional[bytes],
    brand_aesthetic: Optional[dict],
    orchestrator,
    clickup,
):
    """
    Process BRANDED_CREATIVE task with dimension loop.
    
    Uses parsed task data from custom fields.
    """
    config = get_config()
    results = []
    
    logger.info(
        "_process_branded_creative_v2 called",
        extra={
            "task_id": task_id,
            "dimensions": dimensions,
            "generation_count": len(generation_urls),
            "context_count": len(context_bytes),
            "has_logo": logo_bytes is not None,
            "has_brand_aesthetic": brand_aesthetic is not None,
        }
    )
    
    if not generation_urls:
        await clickup.update_task_status(
            task_id=task_id,
            status="blocked",
            comment="❌ **No images to include**\n\nNo main images provided."
        )
        return
    
    # Loop through dimensions
    for i, dimension in enumerate(dimensions):
        logger.info(
            f"Processing dimension {i + 1}/{len(dimensions)}: {dimension}",
            extra={"task_id": task_id, "dimension": dimension}
        )
        
        try:
            if i == 0:
                # First dimension: use original attachments
                gen_prompt = _build_branded_prompt_v2(parsed_task, dimension, brand_aesthetic)
                image_url = generation_urls[0]
                image_bytes = generation_bytes[0]
                additional_urls = generation_urls[1:] if len(generation_urls) > 1 else None
                additional_bytes = generation_bytes[1:] if len(generation_bytes) > 1 else None
                ctx_bytes = context_bytes
            else:
                # Subsequent dimensions: adapt from previous result
                gen_prompt = _build_adapt_prompt_v2()
                image_url = results[-1].final_image.temp_url
                image_bytes = results[-1].final_image.image_bytes
                additional_urls = None
                additional_bytes = None
                ctx_bytes = None
            
            result = await orchestrator.process_with_iterations(
                task_id=task_id,
                prompt=gen_prompt,
                original_image_url=image_url,
                original_image_bytes=image_bytes,
                task_type="BRANDED_CREATIVE",
                additional_image_urls=additional_urls,
                additional_image_bytes=additional_bytes,
                context_image_bytes=ctx_bytes,
            )
            
            if result.status == "success":
                results.append(result)
                logger.info(
                    f"Dimension {dimension} complete",
                    extra={
                        "task_id": task_id,
                        "model": result.final_image.model_name,
                    }
                )
            else:
                logger.warning(
                    f"Dimension {dimension} failed",
                    extra={"task_id": task_id}
                )
        
        except Exception as e:
            logger.error(
                f"Dimension {dimension} error: {e}",
                extra={"task_id": task_id, "dimension": dimension}
            )
    
    # Upload results
    if results:
        for i, result in enumerate(results):
            dim_label = dimensions[i].replace(":", "x")
            
            await clickup.upload_attachment(
                task_id=task_id,
                image_bytes=result.final_image.image_bytes,
                filename=f"edited_{task_id}_{dim_label}.png",
            )
        
        dims_done = [dimensions[i] for i in range(len(results))]
        dims_failed = [d for d in dimensions if d not in dims_done]
        
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
            status="blocked",
            comment="❌ **All dimensions failed**\n\nNo successful outputs generated."
        )


def _build_branded_prompt_v2(parsed_task: ParsedTask, dimension: str, brand_aesthetic: Optional[dict] = None) -> str:
    """Build prompt for branded creative generation from parsed task."""
    parts = []
    
    # Dimension with framing principle
    if dimension:
        parts.append(f"Create a {dimension} marketing graphic.")
        parts.append("""
Professional marketing graphics fill the entire canvas edge-to-edge.
Empty borders, padding, or letterboxing indicate technical failure, not intentional design.
When adapting to an aspect ratio: expand flexible elements (backgrounds, negative space) to fill the frame - never compress content or add empty bands.""")
    else:
        parts.append("Create a marketing graphic.")
    
    # Main text
    if parsed_task.main_text:
        parts.append(f"\nPrimary text: \"{parsed_task.main_text}\"")
    
    # Secondary text
    if parsed_task.secondary_text:
        parts.append(f"Secondary text: \"{parsed_task.secondary_text}\"")
    
    # Font
    if parsed_task.font:
        parts.append(f"\nFont: {parsed_task.font}")
    
    # Style direction
    if parsed_task.style_direction:
        parts.append(f"\nStyle direction: {parsed_task.style_direction}")
    
    # Extra notes
    if parsed_task.extra_notes:
        parts.append(f"\nAdditional instructions: {parsed_task.extra_notes}")
    
    # =====================================================================
    # CRITICAL: Explicit image role mapping to prevent hallucination
    # =====================================================================
    main_count = len(parsed_task.main_image)
    additional_count = len(parsed_task.additional_images)
    logo_count = len(parsed_task.logo)
    ref_count = len(parsed_task.reference_images)
    
    parts.append("\n" + "=" * 60)
    parts.append("IMAGE ROLES (CRITICAL - READ CAREFULLY):")
    parts.append("=" * 60)
    
    current_idx = 1
    
    # Main images - INCLUDE
    if main_count > 0:
        if main_count == 1:
            parts.append(f"• Image {current_idx}: MAIN CONTENT")
            parts.append(f"  → Primary image. Use as the main visual in output.")
        else:
            parts.append(f"• Images {current_idx}-{current_idx + main_count - 1}: MAIN CONTENT")
            parts.append(f"  → Primary images. Include all in output composition.")
        current_idx += main_count
    
    # Additional images - INCLUDE
    if additional_count > 0:
        if additional_count == 1:
            parts.append(f"• Image {current_idx}: ADDITIONAL CONTENT")
            parts.append(f"  → Include in output alongside main content.")
        else:
            parts.append(f"• Images {current_idx}-{current_idx + additional_count - 1}: ADDITIONAL CONTENT")
            parts.append(f"  → Include all in output alongside main content.")
        current_idx += additional_count
    
    # Logo - INCLUDE
    if logo_count > 0:
        parts.append(f"• Image {current_idx}: BRAND LOGO")
        parts.append(f"  → Place in output. Position per user instructions or brand-appropriate location.")
        current_idx += logo_count
    
    # Reference images - DO NOT INCLUDE
    if ref_count > 0:
        if ref_count == 1:
            parts.append(f"• Image {current_idx}: ⚠️ REFERENCE ONLY ⚠️")
            parts.append(f"  → Style/layout inspiration. Do NOT include its content in output!")
        else:
            parts.append(f"• Images {current_idx}-{current_idx + ref_count - 1}: ⚠️ REFERENCE ONLY ⚠️")
            parts.append(f"  → Style/layout inspiration. Do NOT include their content in output!")
    
    parts.append("=" * 60)
    
    # Summary
    include_count = main_count + additional_count + logo_count
    parts.append(f"\nOutput must contain: {include_count} image(s) + text overlay.")
    if ref_count > 0:
        parts.append(f"Reference images are for inspiration only.")
    
    # Brand aesthetic
    if brand_aesthetic:
        guidance = brand_aesthetic.get("prompt_guidance")
        if guidance:
            parts.append(f"\nBrand guidance: {guidance}")
    
    return "\n".join(parts)


def _build_adapt_prompt_v2() -> str:
    """Build adaptation prompt for subsequent dimensions."""
    return "Recreate this exact image. Keep everything exactly the same. Do not change anything."


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
    
    # 🔍 DEBUG: Log what we received
    logger.info(
        "🔍 DEBUG: _process_branded_creative called",
        extra={
            "task_id": task_id,
            "downloaded_attachments_count": len(downloaded_attachments),
            "attachment_urls_dict": {k: v[:50] + "..." if v else None for k, v in attachment_urls.items()},
            "classified_images": [
                {"index": img.index, "desc": img.description[:50] if img.description else None}
                for img in classified.images
            ],
            "task_type": classified.task_type.value,
            "dimensions": classified.dimensions,
            "brief_summary": classified.brief.summary if classified.brief else None,
            "fonts": classified.fonts,
        }
    )
    
    # ================================================================
    # SEPARATE: Include vs Reference-only images
    # ================================================================
    reference_indices = set()
    
    # Sketch is reference only (used for layout guidance, not generation)
    if classified.extracted_layout:
        reference_indices.add(classified.extracted_layout.from_index)
        logger.info(
            f"🎨 Image {classified.extracted_layout.from_index} is SKETCH (reference only)",
            extra={
                "task_id": task_id,
                "index": classified.extracted_layout.from_index,
                "purpose": "layout_reference",
            }
        )
    
    # Inspiration is reference only (used for style guidance, not generation)
    if classified.extracted_style:
        reference_indices.add(classified.extracted_style.from_index)
        logger.info(
            f"🎨 Image {classified.extracted_style.from_index} is INSPIRATION (reference only)",
            extra={
                "task_id": task_id,
                "index": classified.extracted_style.from_index,
                "purpose": "style_reference",
            }
        )
    
    logger.info(
        f"🔍 Reference indices to exclude from generation: {reference_indices}",
        extra={"task_id": task_id, "reference_indices": list(reference_indices)}
    )
    
    # Split images into:
    # - include_*: Go to WaveSpeed for generation
    # - all_bytes: Go to Claude for enhancement context (ALL images)
    include_urls = []
    include_bytes = []
    all_bytes = []  # ALL images for Claude context
    
    for idx in range(len(downloaded_attachments)):
        filename, bytes_data = downloaded_attachments[idx]
        
        # ALL images go to Claude for context
        all_bytes.append(bytes_data)
        
        # Only NON-reference images go to WaveSpeed
        if idx not in reference_indices:
            if idx in attachment_urls and attachment_urls[idx]:
                include_urls.append(attachment_urls[idx])
                include_bytes.append(bytes_data)
                logger.info(
                    f"✅ Image {idx} ({filename}) → INCLUDE in generation",
                    extra={"task_id": task_id, "index": idx, "file_name": filename}
                )
            else:
                logger.warning(
                    f"⚠️ Image {idx} has no URL, skipping",
                    extra={"task_id": task_id, "index": idx}
                )
        else:
            logger.info(
                f"📌 Image {idx} ({filename}) → REFERENCE only (Claude context, not WaveSpeed)",
                extra={"task_id": task_id, "index": idx, "file_name": filename}
            )
    
    logger.info(
        "🔍 DEBUG: Image split complete",
        extra={
            "task_id": task_id,
            "total_images": len(downloaded_attachments),
            "include_count": len(include_urls),
            "reference_count": len(reference_indices),
            "all_for_context": len(all_bytes),
        }
    )
    
    if not include_urls:
        await clickup.update_task_status(
            task_id=task_id,
            status="blocked",
            comment="❌ **No images to include**\n\nNo attachments marked for output."
        )
        return
    
    # ✅ Derive dimensions from PRIMARY input image if not specified
    if classified.dimensions:
        dimensions = classified.dimensions
        logger.info(
            f"📐 Using specified dimensions: {dimensions}",
            extra={"task_id": task_id, "dimensions": dimensions}
        )
    else:
        # Use PRIMARY image for dimensions
        primary_index = classified.primary_image_index
        
        # Validate index is within bounds
        if primary_index >= len(include_bytes):
            primary_index = 0
            logger.warning(
                f"📐 Primary index {classified.primary_image_index} out of bounds, using 0",
                extra={"task_id": task_id}
            )
        
        primary_bytes = include_bytes[primary_index] if include_bytes else None
        
        if primary_bytes:
            derived_ratio = get_closest_aspect_ratio(primary_bytes)
            dimensions = [derived_ratio]
            logger.info(
                f"📐 No dimensions specified, derived from primary image (index {primary_index}): {derived_ratio}",
                extra={
                    "task_id": task_id,
                    "primary_index": primary_index,
                    "derived_dimension": derived_ratio,
                }
            )
        else:
            dimensions = ["1:1"]
            logger.info(
                "📐 No dimensions specified, using default: 1:1",
                extra={"task_id": task_id}
            )
    
    logger.info(
        f"📐 Dimensions to process: {dimensions}",
        extra={"task_id": task_id, "dimensions": dimensions, "count": len(dimensions)}
    )
    
    # Loop through dimensions
    for i, dimension in enumerate(dimensions):
        logger.info(
            f"Processing dimension {i + 1}/{len(dimensions)}: {dimension}",
            extra={"task_id": task_id, "dimension": dimension}
        )
        
        try:
            if i == 0:
                # First dimension: use original attachments
                prompt = _build_branded_prompt(classified, dimension)
                image_url = include_urls[0]  # Primary image for generation
                image_bytes = include_bytes[0]
                additional_urls = include_urls[1:] if len(include_urls) > 1 else None
                additional_bytes = include_bytes[1:] if len(include_bytes) > 1 else None
                # ✅ NEW: ALL images for Claude enhancement context (includes reference)
                context_bytes = all_bytes
            else:
                # Subsequent dimensions: adapt from previous result
                prompt = _build_adapt_prompt(classified, dimension)
                image_url = results[-1].final_image.temp_url
                image_bytes = results[-1].final_image.image_bytes
                additional_urls = None
                additional_bytes = None
                context_bytes = None  # No extra context for adaptations
            
            # Use orchestrator with separate context
            result = await orchestrator.process_with_iterations(
                task_id=task_id,
                prompt=prompt,
                original_image_url=image_url,
                original_image_bytes=image_bytes,
                task_type="BRANDED_CREATIVE",
                additional_image_urls=additional_urls,      # → WaveSpeed only
                additional_image_bytes=additional_bytes,    # → WaveSpeed only
                context_image_bytes=context_bytes,          # ✅ NEW: → Claude only
            )
            
            if result.status == "success":
                results.append(result)
                logger.info(
                    f"Dimension {dimension} complete",
                    extra={
                        "task_id": task_id, 
                        "model": result.final_image.model_name,
                        "temp_url": result.final_image.temp_url[:100] if result.final_image.temp_url else None
                    }
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
            dimension = dimensions[i]  # ✅ USE LOCAL VARIABLE
            dim_label = dimension.replace(":", "x")
            
            await clickup.upload_attachment(
                task_id=task_id,
                image_bytes=result.final_image.image_bytes,
                filename=f"edited_{task_id}_{dim_label}.png",
            )
        
        # ✅ Checkbox uncheck moved to finally block in process_edit_request
        
        dims_done = [dimensions[i] for i in range(len(results))]  # ✅ USE LOCAL VARIABLE
        dims_failed = [d for d in dimensions if d not in dims_done]  # ✅ USE LOCAL VARIABLE
        
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
    """Build prompt for branded creative generation."""
    parts = []
    
    # Dimension with framing principle
    if dimension:
        parts.append(f"Create a {dimension} marketing graphic.")
        parts.append("""
Professional marketing graphics fill the entire canvas edge-to-edge.
Empty borders, padding, or letterboxing indicate technical failure, not intentional design.
When adapting to an aspect ratio: expand flexible elements (backgrounds, negative space) to fill the frame - never compress content or add empty bands.""")
    else:
        parts.append("Create a marketing graphic.")
    
    # User's request summary
    if classified.brief.summary:
        parts.append(f"\nTask: {classified.brief.summary}")
    
    # Text content
    if classified.brief.text_content:
        parts.append("\nText to include:")
        for text in classified.brief.text_content:
            parts.append(f"  - \"{text}\"")
    
    # Style hints
    if classified.brief.style_hints:
        parts.append(f"\nStyle: {classified.brief.style_hints}")
    
    # Fonts
    if classified.fonts:
        parts.append(f"\nTypography: {classified.fonts}")
    
    # Layout from sketch
    if classified.extracted_layout:
        parts.append(f"\nLayout guide: {classified.extracted_layout.positions}")
    
    # Image descriptions - SEPARATE BY ROLE
    if classified.images:
        # Determine reference indices
        reference_indices = set()
        if classified.extracted_layout:
            reference_indices.add(classified.extracted_layout.from_index)
        if classified.extracted_style:
            reference_indices.add(classified.extracted_style.from_index)
        
        # Split by role
        content_images = [img for img in classified.images if img.index not in reference_indices]
        reference_images = [img for img in classified.images if img.index in reference_indices]
        
        if content_images:
            parts.append("\n📷 CONTENT IMAGES:")
            for img in content_images:
                parts.append(f"  - Image {img.index}: {img.description}")
        
        if reference_images:
            parts.append("\n🎯 STYLE/LAYOUT REFERENCE (follow this):")
            for img in reference_images:
                parts.append(f"  - Image {img.index}: {img.description}")
    
    # Style from inspiration - make it actionable
    if classified.extracted_style:
        parts.append(f"\nFollow this style: {classified.extracted_style.style}")
    
    # Brand aesthetic (from brand_analyzer, if available)
    if classified.brand_aesthetic:
        if isinstance(classified.brand_aesthetic, dict):
            guidance = classified.brand_aesthetic.get("prompt_guidance")
            if guidance:
                parts.append(f"\nBrand guidance: {guidance}")
    
    return "\n".join(parts)


def _build_adapt_prompt(classified: ClassifiedTask, dimension: str) -> str:
    """Build adaptation prompt for subsequent dimensions."""
    return f"""Recreate this exact image in {dimension} format.
                Keep everything identical"""