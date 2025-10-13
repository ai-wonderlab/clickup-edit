# 🎨 Workflow Visualization

## Complete Flow Diagram

```
┌───────────────────────────────────────────────────────────────┐
│                        USER ACTIONS                            │
│  1. Create ClickUp Task                                        │
│  2. Upload Image                                               │
│  3. Write Description (simple, e.g., "make background blue")  │
│  4. Set Custom Field = "Pending"                               │
└───────────────┬───────────────────────────────────────────────┘
                │
                │ ClickUp Webhook
                ▼
┌───────────────────────────────────────────────────────────────┐
│                     FLASK SERVER (app.py)                      │
│                    http://localhost:5000                       │
└───────────────┬───────────────────────────────────────────────┘
                │
                ▼
    ┌──────────────────────┐
    │   /webhook endpoint  │
    │  Receives POST data  │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │  Validate Trigger    │
    │  Check Custom Field  │
    │  Value = "Pending"?  │
    └──────────┬───────────┘
               │ YES
               ▼
    ┌──────────────────────────────────┐
    │  STEP 1: Get Task Details        │
    │  ClickUp API: GET /task/{id}     │
    │  - Get attachments               │
    │  - Get description               │
    └──────────┬───────────────────────┘
               │
               ▼
    ┌──────────────────────────────────┐
    │  STEP 2: Download Image          │
    │  - Find first image attachment   │
    │  - Download to memory (bytes)    │
    └──────────┬───────────────────────┘
               │
               ▼
    ┌──────────────────────────────────┐
    │  STEP 3: Format Prompt           │
    │  OpenRouter → Gemini             │
    │                                  │
    │  Input:                          │
    │  - deep_research.txt template    │
    │  - User's simple description     │
    │                                  │
    │  Output:                         │
    │  - Professional formatted prompt │
    └──────────┬───────────────────────┘
               │
               ▼
    ┌──────────────────────────────────┐
    │  STEP 4: Edit Image              │
    │  WaveSpeed.ai SeaDream v4        │
    │                                  │
    │  Input:                          │
    │  - Original image (base64)       │
    │  - Formatted prompt from Gemini  │
    │                                  │
    │  Processing:                     │
    │  - AI image editing              │
    │  - ~30-60 seconds                │
    │                                  │
    │  Output:                         │
    │  - Edited image (base64)         │
    └──────────┬───────────────────────┘
               │
               ▼
    ┌──────────────────────────────────┐
    │  STEP 5: Upload to ClickUp       │
    │  ClickUp API: POST /attachment   │
    │  - Attach edited image to task   │
    └──────────┬───────────────────────┘
               │
               ▼
    ┌──────────────────────────────────┐
    │  STEP 6: Update Status           │
    │  ClickUp API: POST /field        │
    │  - Clear custom field (or "Done")│
    │  - Marks task as complete        │
    └──────────┬───────────────────────┘
               │
               ▼
        ┌─────────────┐
        │  ✅ SUCCESS  │
        │  All Done!   │
        └─────────────┘
```

## API Integration Points

### 1. ClickUp API
**Endpoints Used:**
- `GET /task/{id}` - Get task details
- `GET /task/{id}/attachment` - Download attachments
- `POST /task/{id}/attachment` - Upload new image
- `POST /task/{id}/field/{field_id}` - Update custom field

**Authentication:**
```
Authorization: {CLICKUP_API_TOKEN}
```

### 2. OpenRouter (Gemini)
**Endpoint:**
- `POST https://openrouter.ai/api/v1/chat/completions`

**Model:**
- `google/gemini-2.0-flash-exp:free`

**Purpose:**
- Transform simple descriptions into professional prompts

**Authentication:**
```
Authorization: Bearer {OPENROUTER_API_KEY}
```

### 3. WaveSpeed.ai (SeaDream v4)
**Endpoint:**
- `POST https://api.wavespeed.ai/v1/models/bytedance/seedream-v4/edit`

**Purpose:**
- AI-powered image editing

**Authentication:**
```
Authorization: Bearer {WAVESPEED_API_KEY}
```

## Example Data Flow

### Input (User)
```json
{
  "task_id": "abc123",
  "description": "make the background blue with sunset colors",
  "image": "photo.jpg",
  "custom_field": "Pending"
}
```

### After Gemini Processing
```json
{
  "formatted_prompt": "Transform the background into a vibrant blue gradient with warm sunset tones featuring golden hour orange and pink hues, maintaining subject focus, photorealistic style, natural lighting, cinematic atmosphere, high detail, 4K quality"
}
```

### After SeaDream Edit
```json
{
  "edited_image": "base64_encoded_image_data...",
  "processing_time": "45s"
}
```

### Final Output (ClickUp)
```json
{
  "task_id": "abc123",
  "attachments": [
    "photo.jpg",           // Original
    "edited_image.png"     // AI-edited
  ],
  "custom_field": ""       // Cleared (complete)
}
```

## Time Estimates

| Step | Average Time |
|------|-------------|
| Webhook Receive | < 1s |
| Download Image | 1-3s |
| Gemini Formatting | 2-5s |
| SeaDream Editing | 30-60s |
| Upload to ClickUp | 2-4s |
| Update Field | < 1s |
| **TOTAL** | **~40-75 seconds** |

## Error Handling

Each step has error handling:
- API failures → Logged and reported
- Image too large → Error message
- Timeout → Retry logic
- No image found → Skip task

All errors are logged to console with timestamps.

## Scaling Considerations

**Current Setup:**
- ✅ Single task processing
- ✅ Sequential workflow
- ✅ Simple deployment

**If High Volume Needed:**
- Queue system (Redis, RabbitMQ)
- Multiple workers
- Database for tracking
- Load balancer

For now, the simple approach is perfect! 🎉