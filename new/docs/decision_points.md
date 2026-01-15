# Decision Points Registry - All Conditionals

## Overview

This document catalogs ALL decision points (conditionals) that affect the flow of the image editing pipeline, including their locations, conditions, and outcomes.

---

## Entry Point Decisions (webhooks.py)

### D1: Signature Verification

| Property | Value |
|----------|-------|
| **File** | `src/api/webhooks.py` |
| **Line** | 345 |
| **Condition** | `not verify_signature(payload_body, signature, secret)` |

```python
if not verify_signature(payload_body, signature, secret):
    raise HTTPException(status_code=401, detail="Invalid signature")
```

| Outcome | Action |
|---------|--------|
| Invalid | Return 401 Unauthorized |
| Valid | Continue processing |

---

### D2: Task ID Present

| Property | Value |
|----------|-------|
| **File** | `src/api/webhooks.py` |
| **Line** | 361 |
| **Condition** | `not task_id` |

```python
if not task_id:
    raise HTTPException(status_code=400, detail="Missing task_id")
```

---

### D3: Event Type Check

| Property | Value |
|----------|-------|
| **File** | `src/api/webhooks.py` |
| **Line** | 364 |
| **Condition** | `event != "taskUpdated"` |

```python
if event != "taskUpdated":
    return {"status": "ignored", "reason": f"Event type {event} not supported"}
```

| Outcome | Action |
|---------|--------|
| Not `taskUpdated` | Ignore webhook |
| `taskUpdated` | Continue processing |

---

### D4: Task Lock Acquisition

| Property | Value |
|----------|-------|
| **File** | `src/api/webhooks.py` |
| **Line** | 374 |
| **Condition** | `not await acquire_task_lock(task_id)` |

```python
if not await acquire_task_lock(task_id):
    return {
        "status": "already_processing",
        "task_id": task_id,
        "message": "Task is already being processed"
    }
```

| Outcome | Action |
|---------|--------|
| Lock unavailable | Reject duplicate |
| Lock acquired | Continue processing |

---

### D5: Task Already Complete

| Property | Value |
|----------|-------|
| **File** | `src/api/webhooks.py` |
| **Line** | 411 |
| **Condition** | `task_status == "complete"` |

```python
if task_status == "complete":
    return {"status": "ignored", "reason": "Task already complete"}
```

---

### D6: Task Status Check

| Property | Value |
|----------|-------|
| **File** | `src/api/webhooks.py` |
| **Line** | 419 |
| **Condition** | `task_status not in ["to do", "todo"]` |

```python
if task_status not in ["to do", "todo"]:
    return {"status": "ignored", "reason": f"Task status is '{task_status}', not 'to do'"}
```

---

### D7: AI Edit Checkbox

| Property | Value |
|----------|-------|
| **File** | `src/api/webhooks.py` |
| **Line** | 436 |
| **Condition** | `not needs_ai_edit` |

```python
if not needs_ai_edit:
    return {"status": "ignored", "reason": "AI Edit checkbox not checked"}
```

---

### D8: Edit Task Validation

| Property | Value |
|----------|-------|
| **File** | `src/api/webhooks.py` |
| **Lines** | 450-456 |
| **Condition** | `parsed.is_edit and not parsed.main_image` |

```python
if parsed.is_edit:
    if not parsed.main_image:
        return {"status": "ignored", "reason": "Edit task requires Main Image"}
```

---

### D9: Creative Task Validation

| Property | Value |
|----------|-------|
| **File** | `src/api/webhooks.py` |
| **Lines** | 457-469 |
| **Condition** | `parsed.is_creative and (not main_image or not main_text)` |

```python
elif parsed.is_creative:
    if not parsed.main_image:
        return {"status": "ignored", "reason": "Creative task requires Main Image"}
    if not parsed.main_text:
        return {"status": "ignored", "reason": "Creative task requires Main Text"}
```

---

### D10: Task Type Routing

| Property | Value |
|----------|-------|
| **File** | `src/api/webhooks.py` |
| **Line** | 741 |
| **Condition** | `parsed_task.is_edit` |

```python
if parsed_task.is_edit:
    # SIMPLE_EDIT flow
    result = await orchestrator.process_with_iterations(
        task_type="SIMPLE_EDIT",
        ...
    )
else:
    # BRANDED_CREATIVE flow
    await _process_branded_creative_v2(...)
```

| Outcome | Action |
|---------|--------|
| `is_edit = True` | SIMPLE_EDIT flow |
| `is_edit = False` | BRANDED_CREATIVE flow |

---

### D11: Brand Website Analysis

| Property | Value |
|----------|-------|
| **File** | `src/api/webhooks.py` |
| **Line** | 726 |
| **Condition** | `parsed_task.brand_website` |

```python
if parsed_task.brand_website:
    brand_result = await brand_analyzer.analyze(parsed_task.brand_website)
    if brand_result:
        brand_aesthetic = brand_result.get("brand_aesthetic")
```

---

### D12: No Valid Images

| Property | Value |
|----------|-------|
| **File** | `src/api/webhooks.py` |
| **Line** | 714 |
| **Condition** | `not main_images` |

```python
if not main_images:
    await clickup.update_task_status(
        task_id=task_id,
        status="blocked",
        comment="❌ **No valid images found**..."
    )
    return
```

---

## Orchestrator Decisions (orchestrator.py)

### D13: Include Image in Enhancement

| Property | Value |
|----------|-------|
| **File** | `src/core/orchestrator.py` |
| **Line** | 197 |
| **Condition** | `iteration == 1` |

```python
include_image = (iteration == 1)

enhanced = await self.enhancer.enhance_all_parallel(
    current_prompt,
    original_images_bytes=enhancement_bytes if include_image else None,
)
```

| Outcome | Action |
|---------|--------|
| First iteration | Include images in enhancement |
| Subsequent | Skip images (already processed) |

---

### D14: Best Result Selection

| Property | Value |
|----------|-------|
| **File** | `src/core/orchestrator.py` |
| **Line** | 308 |
| **Condition** | `best_result` (not None) |

```python
best_result = self.select_best_result(validated, generated)

if best_result:
    # SUCCESS!
    return ProcessResult(
        status=ProcessStatus.SUCCESS,
        final_image=best_result,
        ...
    )
```

---

### D15: Switch to Sequential Mode

| Property | Value |
|----------|-------|
| **File** | `src/core/orchestrator.py` |
| **Line** | 334 |
| **Condition** | `iteration >= 3` |

```python
if iteration >= 3:
    # Failed 3 times - try sequential breakdown
    steps = self.refiner.parse_request_into_steps(prompt)
    
    if len(steps) > 1:
        # Execute sequentially
        final_image = await self.refiner.execute_sequential(...)
```

| Outcome | Action |
|---------|--------|
| 3+ iterations failed | Try sequential mode |
| < 3 iterations | Continue normal iteration |

---

### D16: Sequential Mode Success

| Property | Value |
|----------|-------|
| **File** | `src/core/orchestrator.py` |
| **Line** | 359 |
| **Condition** | `final_image` (from sequential) |

```python
if final_image:
    return ProcessResult(
        status=ProcessStatus.SUCCESS,
        final_image=final_image,
        model_used=f"{final_image.model_name} (sequential)",
        ...
    )
else:
    logger.error("Sequential mode also failed")
    break  # Continue to hybrid fallback
```

---

### D17: Can Break Down Request

| Property | Value |
|----------|-------|
| **File** | `src/core/orchestrator.py` |
| **Line** | 344 |
| **Condition** | `len(steps) > 1` |

```python
if len(steps) > 1:
    # Execute sequentially
    ...
else:
    logger.info("Request is single operation - cannot break down further")
```

---

### D18: Continue Refinement

| Property | Value |
|----------|-------|
| **File** | `src/core/orchestrator.py` |
| **Line** | 378 |
| **Condition** | `iteration < self.max_iterations` |

```python
if iteration < self.max_iterations:
    # Phase 5: Refinement
    refinement = await self.refiner.refine_with_feedback(...)
```

---

### D19: Refinement Success Check

| Property | Value |
|----------|-------|
| **File** | `src/core/orchestrator.py` |
| **Line** | 397 |
| **Condition** | `refinement.validated` |

```python
if refinement.validated:
    best_refined = self.select_best_result(
        refinement.validated,
        refinement.generated
    )
    
    if best_refined:
        return ProcessResult(status=ProcessStatus.SUCCESS, ...)
```

---

## Validation Decisions (validator.py)

### D20: Validation Prompt Selection

| Property | Value |
|----------|-------|
| **File** | `src/core/validator.py` |
| **Line** | 110 |
| **Condition** | `task_type == "BRANDED_CREATIVE"` |

```python
if task_type == "BRANDED_CREATIVE":
    base_prompt = self.validation_prompt_branded or self.validation_prompt_template
    prompt_source = "branded"
else:
    base_prompt = self.validation_prompt_template
    prompt_source = "default"
```

---

### D21: Pass/Fail Determination

| Property | Value |
|----------|-------|
| **File** | `src/providers/openrouter.py` |
| **Line** | 616 |
| **Condition** | `result_data["pass_fail"] == "PASS"` |

```python
return ValidationResult(
    model_name=model_name,
    passed=(result_data["pass_fail"] == "PASS"),
    score=result_data["score"],
    ...
)
```

---

### D22: Score Threshold Override

| Property | Value |
|----------|-------|
| **File** | `src/providers/openrouter.py` |
| **Line** | 771 |
| **Condition** | `score >= config.validation_pass_threshold` |

```python
expected_pass = "PASS" if score >= config.validation_pass_threshold else "FAIL"
if pass_fail != expected_pass:
    # Override with score-based logic
    pass_fail = expected_pass
```

---

## Refiner Decisions (refiner.py)

### D23: Sequential Step Success

| Property | Value |
|----------|-------|
| **File** | `src/core/refiner.py` |
| **Line** | 309 |
| **Condition** | `passing` (list not empty) |

```python
passing = [v for v in validated if v.passed]

if passing:
    # SUCCESS! Select highest scoring result
    best_validation = max(passing, key=lambda v: v.score)
    step_succeeded = True
    break  # Exit retry loop
```

---

### D24: Step Retry Decision

| Property | Value |
|----------|-------|
| **File** | `src/core/refiner.py` |
| **Line** | 355 |
| **Condition** | `attempt >= max_step_attempts` |

```python
if attempt >= max_step_attempts:
    # All attempts exhausted
    logger.error(f"❌ STEP {i} FAILED after {max_step_attempts} attempts")
    return None
else:
    # Will retry
    continue
```

---

### D25: Preservation Clause Detection

| Property | Value |
|----------|-------|
| **File** | `src/core/refiner.py` |
| **Line** | 177 |
| **Condition** | `"Όλα τα υπολοιπα" in request` |

```python
if "Όλα τα υπολοιπα" in request:
    parts = request.split("Όλα τα υπολοιπα")
    request_part = parts[0].strip()
    preservation = "Όλα τα υπολοιπα" + parts[1]
else:
    request_part = request.strip()
    preservation = "Όλα τα υπολοιπα να μεινουνε ακριβως ιδια"
```

---

## Task Parser Decisions (task_parser.py)

### D26: Task Type Dropdown Parsing

| Property | Value |
|----------|-------|
| **File** | `src/core/task_parser.py` |
| **Line** | 145 |
| **Condition** | `isinstance(value, int) and 0 <= value < len(options)` |

```python
if isinstance(value, int) and 0 <= value < len(options):
    return options[value].get("name", "Edit")

# If value is already the option ID, find it
if isinstance(value, str):
    for opt in options:
        if opt.get("id") == value:
            return opt.get("name", "Edit")

return "Edit"  # Default
```

---

### D27: Prompt Builder Routing

| Property | Value |
|----------|-------|
| **File** | `src/core/task_parser.py` |
| **Line** | 240 |
| **Condition** | `parsed.is_edit` |

```python
if parsed.is_edit:
    return self._build_edit_prompt(parsed)
else:
    return self._build_creative_prompt(parsed)
```

---

## Lock Management Decisions (webhooks.py)

### D28: Stale Lock Detection

| Property | Value |
|----------|-------|
| **File** | `src/api/webhooks.py` |
| **Line** | 147 |
| **Condition** | `age_seconds > LOCK_TTL_SECONDS` |

```python
if age_seconds > LOCK_TTL_SECONDS:
    # Clean it up and allow re-acquisition
    if lock.locked():
        lock.release()
    del _task_locks[task_id]
    # Fall through to create new lock
```

---

### D29: Periodic Cleanup Trigger

| Property | Value |
|----------|-------|
| **File** | `src/api/webhooks.py` |
| **Line** | 131 |
| **Condition** | `_acquire_counter % CLEANUP_CHECK_INTERVAL == 0` |

```python
if _acquire_counter % CLEANUP_CHECK_INTERVAL == 0:
    should_cleanup = True
```

---

## Image Processing Decisions

### D30: Image Resize for Context

| Property | Value |
|----------|-------|
| **File** | `src/providers/openrouter.py` |
| **Line** | 423 |
| **Condition** | `len(original_bytes) > MAX_SIZE_FOR_CLAUDE` |

```python
if len(original_bytes) > MAX_SIZE_FOR_CLAUDE:
    original_bytes = resize_for_context(
        original_bytes,
        max_dimension=2048,
        quality=85
    )
```

---

### D31: Image Format Detection

| Property | Value |
|----------|-------|
| **File** | `src/providers/openrouter.py` |
| **Line** | 478 |
| **Condition** | `image_format == 'JPEG'` |

```python
if image_format == 'JPEG':
    # Keep as-is
    edited_data_url = f"data:image/jpeg;base64,{edited_b64}"
else:
    # Convert to JPEG
    edited_img = edited_img.convert('RGB')
    edited_img.save(jpeg_buffer, format='JPEG', quality=90)
```

---

## Branded Creative Decisions (webhooks.py)

### D32: First vs Subsequent Dimension

| Property | Value |
|----------|-------|
| **File** | `src/api/webhooks.py` |
| **Line** | 915 |
| **Condition** | `i == 0` |

```python
if i == 0:
    # First dimension: use original attachments
    gen_prompt = _build_branded_prompt_v2(parsed_task, dimension, brand_aesthetic)
    image_url = generation_urls[0]
    image_bytes = generation_bytes[0]
    additional_urls = generation_urls[1:] if len(generation_urls) > 1 else None
else:
    # Subsequent dimensions: adapt from previous result
    gen_prompt = _build_adapt_prompt_v2(dimension)
    image_url = results[-1].final_image.temp_url
    image_bytes = results[-1].final_image.image_bytes
    additional_urls = None
```

---

### D33: Dimension Result Handling

| Property | Value |
|----------|-------|
| **File** | `src/api/webhooks.py` |
| **Line** | 944 |
| **Condition** | `result.status == "success"` |

```python
if result.status == "success":
    results.append(result)
else:
    logger.warning(f"Dimension {dimension} failed")
    # Continue with other dimensions
```

---

### D34: All Dimensions Failed

| Property | Value |
|----------|-------|
| **File** | `src/api/webhooks.py` |
| **Line** | 992 |
| **Condition** | `not results` |

```python
if results:
    # Upload results and mark complete
    ...
else:
    await clickup.update_task_status(
        task_id=task_id,
        status="blocked",
        comment="❌ **All dimensions failed**..."
    )
```

---

## Error Handling Decisions

### D35: Validation System Error

| Property | Value |
|----------|-------|
| **File** | `src/core/orchestrator.py` |
| **Line** | 250 |
| **Condition** | `iteration == self.max_iterations` (after validation error) |

```python
except Exception as validation_error:
    if iteration == self.max_iterations:
        logger.error("Validation failed in final iteration, triggering hybrid fallback")
        break
    else:
        logger.warning(f"Validation failed, retrying iteration {iteration + 1}")
        continue
```

---

### D36: Critical Failure Handling

| Property | Value |
|----------|-------|
| **File** | `src/core/orchestrator.py` |
| **Line** | 461 |
| **Condition** | `iteration == self.max_iterations` (after AllEnhancementsFailed/AllGenerationsFailed) |

```python
except (AllEnhancementsFailed, AllGenerationsFailed) as e:
    if iteration == self.max_iterations:
        break  # Fall through to hybrid fallback
    continue  # Try next iteration
```

---

## Decision Flow Summary

```
Webhook Entry
    │
    ├─D1─> Invalid signature? → 401
    ├─D2─> No task_id? → 400
    ├─D3─> Not taskUpdated? → Ignore
    ├─D4─> Lock unavailable? → Already processing
    ├─D5─> Already complete? → Ignore
    ├─D6─> Not "to do"? → Ignore
    ├─D7─> No AI checkbox? → Ignore
    │
    ├─D8/D9─> Missing required fields? → Ignore
    │
    ├─D10─> Task Type?
    │       ├─ Edit → SIMPLE_EDIT flow
    │       └─ Creative → BRANDED_CREATIVE flow
    │
    └─D11─> Brand website? → Analyze

Orchestrator Loop
    │
    ├─D13─> First iteration? → Include images
    │
    ├─D14─> Best result found? → SUCCESS
    │
    ├─D15─> 3+ iterations? → Try sequential
    │       ├─D16─> Sequential success? → SUCCESS
    │       └─D17─> Can break down? → Execute steps
    │
    ├─D18─> More iterations? → Refine
    │       └─D19─> Refinement success? → SUCCESS
    │
    └─ All failed → Hybrid Fallback

Sequential Mode
    │
    ├─D23─> Step passed? → Next step
    │
    ├─D24─> Max attempts? → Fail
    │
    └─ All steps done → SUCCESS

Validation
    │
    ├─D20─> Task type? → Select prompt
    │
    ├─D21─> PASS/FAIL from response
    │
    └─D22─> Score override threshold
```

