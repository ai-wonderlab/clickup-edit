# API Calls Registry - All External API Payloads

## Overview

This document catalogs ALL external API calls made by the image editing pipeline, including exact payload structures, headers, and response handling.

---

## 1. OpenRouter API (Claude)

### Base Configuration

| Property | Value |
|----------|-------|
| **Base URL** | `https://openrouter.ai/api/v1` |
| **Auth Method** | Bearer Token |
| **Timeout** | 120 seconds (configurable) |

### Headers

```python
{
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://image-edit-agent.com",
    "X-Title": "Image Edit Agent",
}
```

---

### API Call 1.1: Prompt Enhancement

| Property | Value |
|----------|-------|
| **Endpoint** | `POST /chat/completions` |
| **File** | `src/providers/openrouter.py` |
| **Lines** | 276-280 |
| **Purpose** | Enhance user prompts for image generation |
| **Retry** | 3 attempts with exponential backoff |

#### Request Payload

```python
payload = {
    "model": "anthropic/claude-sonnet-4.5",
    "messages": [
        {
            "role": "system",
            "content": system_prompt  # Deep research + fonts guide
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": user_text  # Enhancement instructions
                },
                # Optional: Images as base64
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{img_b64}"
                    }
                }
            ]
        }
    ],
    "max_tokens": 2000,
    # temperature removed - defaults to 1.0 (required for thinking)
    
    "reasoning": {
        "effort": "high"  # Enable Claude thinking mode
    },
    
    "provider": {
        "order": ["Anthropic"],
        "allow_fallbacks": False  # Lock to Anthropic
    }
}
```

#### Response Structure

```json
{
    "id": "gen-xxx",
    "model": "anthropic/claude-sonnet-4.5",
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": "Enhanced prompt text..."
            },
            "finish_reason": "stop"
        }
    ],
    "usage": {
        "prompt_tokens": 1234,
        "completion_tokens": 567,
        "total_tokens": 1801
    }
}
```

---

### API Call 1.2: Image Validation

| Property | Value |
|----------|-------|
| **Endpoint** | `POST /chat/completions` |
| **File** | `src/providers/openrouter.py` |
| **Lines** | 558-561 |
| **Purpose** | Validate generated images against requirements |
| **Retry** | 3 attempts with exponential backoff |

#### Request Payload

```python
payload = {
    "model": "anthropic/claude-sonnet-4.5",
    "messages": [
        {
            "role": "system",
            "content": validation_prompt_template  # Full validation prompt
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": user_text  # "Validate this edit..."
                },
                # Original image(s) - base64 encoded
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{original_b64}"
                    }
                },
                # Edited image - base64 encoded (LAST)
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{edited_b64}"
                    }
                }
            ]
        }
    ],
    "max_tokens": 2000,
    
    "reasoning": {
        "effort": "high"
    },
    
    "provider": {
        "order": ["Anthropic"],
        "allow_fallbacks": False
    }
}
```

#### Expected Response (JSON in content)

```json
{
    "pass_fail": "PASS",
    "score": 9,
    "issues": ["No issues found"],
    "reasoning": "Detailed comparison explanation..."
}
```

---

### API Call 1.3: Brand Analysis (with Web Search)

| Property | Value |
|----------|-------|
| **Endpoint** | `POST /chat/completions` |
| **File** | `src/core/brand_analyzer.py` |
| **Lines** | 188-192 |
| **Purpose** | Analyze brand website for aesthetic guidelines |
| **Timeout** | 60 seconds (extended for web search) |

#### Request Payload

```python
payload = {
    "model": "anthropic/claude-sonnet-4.5:online",  # :online enables web search
    "messages": [
        {
            "role": "system",
            "content": brand_analyzer_prompt  # From file
        },
        {
            "role": "user",
            "content": f"Analyze this brand's website...\n\nWEBSITE URL: {url}"
        }
    ],
    "max_tokens": 2000,
    "temperature": 0.0,
    
    # OpenRouter web search plugin
    "plugins": [
        {
            "id": "web",
            "engine": "native",  # Uses Anthropic's native web search
            "max_results": 5
        }
    ]
}
```

#### Expected Response (JSON in content)

```json
{
    "brand_aesthetic": {
        "style": "minimal, elegant",
        "mood": "sophisticated, premium",
        "typography": {...},
        "colors": {...},
        "layout": {...},
        "promotional_style": {...},
        "design_principles": [...]
    },
    "prompt_guidance": "Single paragraph describing style..."
}
```

---

## 2. WaveSpeed API (Image Generation)

### Base Configuration

| Property | Value |
|----------|-------|
| **Base URL** | `https://api.wavespeed.ai/api/v3` |
| **Auth Method** | Bearer Token |
| **Timeout** | 300 seconds (configurable) |

### Headers

```python
{
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}
```

---

### API Call 2.1: Submit Generation Task

| Property | Value |
|----------|-------|
| **Endpoint** | `POST /{model_id}` |
| **File** | `src/providers/wavespeed.py` |
| **Lines** | 128-131 |
| **Purpose** | Submit image generation task |
| **Retry** | 3 attempts with exponential backoff |

#### Model Endpoints

| Model Name | Endpoint |
|------------|----------|
| `seedream-v4` | `bytedance/seedream-v4/edit` |
| `qwen-edit-plus` | `wavespeed-ai/qwen-image/edit-plus` |
| `wan-2.5-edit` | `alibaba/wan-2.5/image-edit` |
| `nano-banana` | `google/nano-banana/edit` |
| `nano-banana-pro-edit` | `google/nano-banana-pro/edit` |
| `nano-banana-pro-edit-ultra` | `google/nano-banana-pro/edit-ultra` |

#### Request Payload (Base)

```python
payload = {
    "images": ["url1", "url2", ...],  # Up to 10 image URLs
    "prompt": "Enhanced prompt text...",
    "enable_base64_output": False,
    "enable_sync_mode": False,  # Async mode
}
```

#### Model-Specific Parameters

```python
# Qwen models
if "qwen" in model_name.lower():
    payload["seed"] = -1
    payload["output_format"] = "jpeg"

# Nano Banana Pro Edit Ultra (4K)
elif model_name == "nano-banana-pro-edit-ultra":
    payload["output_format"] = "png"
    payload["resolution"] = "4k"

# Nano Banana Pro Edit (1K)
elif model_name == "nano-banana-pro-edit":
    payload["output_format"] = "png"
    payload["resolution"] = "1k"

# Nano Banana (standard)
elif "nano-banana" in model_name.lower():
    payload["output_format"] = "jpeg"

# Wan models
elif "wan" in model_name.lower():
    payload["seed"] = -1

# Optional: Aspect ratio
if aspect_ratio:
    payload["aspect_ratio"] = aspect_ratio  # e.g., "16:9", "1:1"
```

#### Response Structure

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "id": "prediction_id_xxx",
        "model": "google/nano-banana-pro/edit",
        "status": "processing"
    }
}
```

---

### API Call 2.2: Poll for Result

| Property | Value |
|----------|-------|
| **Endpoint** | `GET /predictions/{task_id}/result` |
| **File** | `src/providers/wavespeed.py` |
| **Lines** | 245-248 |
| **Purpose** | Check generation task status |
| **Poll Interval** | 2 seconds |
| **Max Wait** | 300 seconds (from timeout config) |

#### Response Structure (Processing)

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "id": "prediction_id_xxx",
        "status": "processing"
    }
}
```

#### Response Structure (Completed)

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "id": "prediction_id_xxx",
        "model": "google/nano-banana-pro/edit",
        "outputs": ["https://cloudfront.xxx/image.png"],
        "status": "completed",
        "has_nsfw_contents": [false],
        "error": "",
        "executionTime": 2500,
        "timings": {
            "inference": 2500
        }
    }
}
```

#### Response Structure (Failed)

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "id": "prediction_id_xxx",
        "status": "failed",
        "error": "Error description..."
    }
}
```

---

### API Call 2.3: Download Generated Image

| Property | Value |
|----------|-------|
| **Endpoint** | `GET {cloudfront_url}` |
| **File** | `src/providers/wavespeed.py` |
| **Lines** | 303-309 |
| **Purpose** | Download generated image bytes |

#### Request

```python
response = await self.client.get(url)
image_bytes = response.content
```

---

## 3. ClickUp API

### Base Configuration

| Property | Value |
|----------|-------|
| **Base URL** | `https://api.clickup.com/api/v2` |
| **Auth Method** | Direct API Key |
| **Timeout** | 30 seconds |

### Headers

```python
{
    "Authorization": api_key,  # Direct key, no Bearer
}
```

---

### API Call 3.1: Get Task

| Property | Value |
|----------|-------|
| **Endpoint** | `GET /task/{task_id}` |
| **File** | `src/providers/clickup.py` |
| **Lines** | 268-273 |
| **Purpose** | Fetch full task data |
| **Retry** | 2 attempts |

#### Response Structure

```json
{
    "id": "task_id",
    "name": "Task Name",
    "description": "Task description...",
    "status": {
        "status": "to do",
        "color": "#87909e"
    },
    "custom_fields": [
        {
            "id": "field_id",
            "name": "AI Edit",
            "type": "checkbox",
            "value": true
        },
        {
            "id": "field_id",
            "name": "Task Type",
            "type": "drop_down",
            "value": 0,
            "type_config": {
                "options": [
                    {"id": "opt1", "name": "Edit"},
                    {"id": "opt2", "name": "Creative"}
                ]
            }
        },
        {
            "id": "field_id",
            "name": "Main Image",
            "type": "attachment",
            "value": [
                {
                    "url": "https://...",
                    "title": "image.png"
                }
            ]
        }
    ],
    "attachments": [...]
}
```

---

### API Call 3.2: Download Attachment

| Property | Value |
|----------|-------|
| **Endpoint** | `GET {attachment_url}` |
| **File** | `src/providers/clickup.py` |
| **Lines** | 60-61 |
| **Purpose** | Download attachment bytes |
| **Retry** | 3 attempts |

---

### API Call 3.3: Upload Attachment

| Property | Value |
|----------|-------|
| **Endpoint** | `POST /task/{task_id}/attachment` |
| **File** | `src/providers/clickup.py` |
| **Lines** | 122-126 |
| **Purpose** | Upload image to task |
| **Retry** | 3 attempts |

#### Request (Multipart)

```python
files = {
    "attachment": (filename, image_bytes, "image/png"),
}

headers = {
    "Authorization": api_key,
}

response = await self.client.post(
    f"{base_url}/task/{task_id}/attachment",
    files=files,
    headers=headers,
)
```

#### Response Structure

```json
{
    "id": "attachment_id",
    "url": "https://attachments.clickup.com/..."
}
```

---

### API Call 3.4: Update Task Status

| Property | Value |
|----------|-------|
| **Endpoint** | `PUT /task/{task_id}` |
| **File** | `src/providers/clickup.py` |
| **Lines** | 200-204 |
| **Purpose** | Update task status |
| **Retry** | 3 attempts |

#### Request Payload

```python
{
    "status": "complete"  # or "in progress", "blocked"
}
```

---

### API Call 3.5: Add Comment

| Property | Value |
|----------|-------|
| **Endpoint** | `POST /task/{task_id}/comment` |
| **File** | `src/providers/clickup.py` |
| **Lines** | 238-241 |
| **Purpose** | Add comment to task |
| **Retry** | 2 attempts |

#### Request Payload

```python
{
    "comment_text": "✅ **Edit completed!**\n\n**Model:** nano-banana-pro-edit\n..."
}
```

---

### API Call 3.6: Update Custom Field

| Property | Value |
|----------|-------|
| **Endpoint** | `POST /task/{task_id}/field/{field_id}` |
| **File** | `src/providers/clickup.py` |
| **Lines** | 287-291 |
| **Purpose** | Update custom field value (e.g., uncheck AI Edit) |

#### Request Payload

```python
{
    "value": False  # or any field value
}
```

---

## Error Handling

### OpenRouter Errors

| Status Code | Error Type | Handling |
|-------------|------------|----------|
| 401 | `AuthenticationError` | Fail immediately |
| 429 | `RateLimitError` | Retry with backoff |
| 4xx/5xx | `ProviderError` | Retry up to 3 times |

### WaveSpeed Errors

| Status Code | Error Type | Handling |
|-------------|------------|----------|
| Non-200 | `ProviderError` | Retry up to 3 times |
| `code != 200` in response | `ProviderError` | Retry |
| `status == "failed"` | `ProviderError` | Fail |
| Timeout | `ProviderError` | Fail |

### ClickUp Errors

| Status Code | Error Type | Handling |
|-------------|------------|----------|
| 401 | `AuthenticationError` | Fail immediately |
| 4xx/5xx | `ProviderError` | Retry up to 3 times |

---

## Rate Limiting

### OpenRouter

| Operation | Semaphore Limit | Source |
|-----------|-----------------|--------|
| Enhancement | 5 concurrent | `config.rate_limit_enhancement` |
| Validation | 3 concurrent | `config.rate_limit_validation` |

### Validation Delay

```python
# Between sequential validations
await asyncio.sleep(config.validation_delay_seconds)  # Default: 2.0
```

---

## API Call Sequence Diagram

```
┌─────────┐     ┌──────────┐     ┌──────────┐     ┌─────────┐
│ Webhook │     │ ClickUp  │     │OpenRouter│     │WaveSpeed│
└────┬────┘     └────┬─────┘     └────┬─────┘     └────┬────┘
     │               │                │                │
     │──GET task────>│                │                │
     │<──task data───│                │                │
     │               │                │                │
     │──GET attach──>│                │                │
     │<──image bytes─│                │                │
     │               │                │                │
     │──POST upload─>│                │                │
     │<──url─────────│                │                │
     │               │                │                │
     │───────────────┼──POST enhance─>│                │
     │               │<──enhanced─────│                │
     │               │                │                │
     │───────────────┼────────────────┼──POST generate>│
     │               │                │<──task_id──────│
     │               │                │                │
     │               │                │──GET poll─────>│
     │               │                │<──processing───│
     │               │                │                │
     │               │                │──GET poll─────>│
     │               │                │<──completed────│
     │               │                │                │
     │               │                │──GET image────>│
     │               │                │<──bytes────────│
     │               │                │                │
     │───────────────┼──POST validate>│                │
     │               │<──JSON result──│                │
     │               │                │                │
     │──POST upload─>│                │                │
     │<──url─────────│                │                │
     │               │                │                │
     │──PUT status──>│                │                │
     │<──ok──────────│                │                │
     │               │                │                │
     │──POST comment>│                │                │
     │<──ok──────────│                │                │
     │               │                │                │
     │──POST field──>│                │                │
     │<──ok──────────│                │                │
```

