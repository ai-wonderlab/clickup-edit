# Configuration Registry - All Parameters

## Overview

This document catalogs ALL configurable parameters in the image editing pipeline, including their locations, default values, and what they control.

---

## Environment Variables

### API Keys (Required)

| Parameter | Env Variable | File | Line | Description |
|-----------|--------------|------|------|-------------|
| `openrouter_api_key` | `OPENROUTER_API_KEY` | `config.py` | 63 | OpenRouter API key for Claude |
| `wavespeed_api_key` | `WAVESPEED_API_KEY` | `config.py` | 64 | WaveSpeed API key for image generation |
| `clickup_api_key` | `CLICKUP_API_KEY` | `config.py` | 65 | ClickUp API key for task management |
| `clickup_webhook_secret` | `CLICKUP_WEBHOOK_SECRET` | `config.py` | 66 | Secret for webhook signature verification |

### ClickUp Settings

| Parameter | Env Variable | Default | File | Line | Description |
|-----------|--------------|---------|------|------|-------------|
| `clickup_custom_field_id_ai_edit` | `CLICKUP_CUSTOM_FIELD_ID_AI_EDIT` | Required | `config.py` | 69 | Custom field ID for AI Edit checkbox |
| `clickup_status_complete` | `CLICKUP_STATUS_COMPLETE` | `"complete"` | `config.py` | 70 | Status to set on successful completion |

### Application Settings

| Parameter | Env Variable | Default | File | Line | Description |
|-----------|--------------|---------|------|------|-------------|
| `app_env` | `APP_ENV` | `"development"` | `config.py` | 73 | Environment (development/production) |
| `log_level` | `LOG_LEVEL` | `"INFO"` | `config.py` | 74 | Logging level |
| `max_iterations` | `MAX_ITERATIONS` | `3` | `config.py` | 75 | Maximum refinement iterations |
| `max_step_attempts` | `MAX_STEP_ATTEMPTS` | `2` | `config.py` | 77 | Max attempts per sequential step |
| `validation_pass_threshold` | `VALIDATION_PASS_THRESHOLD` | `8` | `config.py` | 78 | Minimum score to pass validation |

### Rate Limiting

| Parameter | Env Variable | Default | File | Line | Description |
|-----------|--------------|---------|------|------|-------------|
| `rate_limit_enhancement` | `RATE_LIMIT_ENHANCEMENT` | `5` | `config.py` | 81 | Max concurrent enhancement calls |
| `rate_limit_validation` | `RATE_LIMIT_VALIDATION` | `3` | `config.py` | 82 | Max concurrent validation calls |

### Timeout Settings

| Parameter | Env Variable | Default | File | Line | Description |
|-----------|--------------|---------|------|------|-------------|
| `timeout_openrouter_seconds` | `TIMEOUT_OPENROUTER_SECONDS` | `120.0` | `config.py` | 85 | OpenRouter API timeout |
| `timeout_wavespeed_seconds` | `TIMEOUT_WAVESPEED_SECONDS` | `300.0` | `config.py` | 86 | WaveSpeed API timeout |
| `validation_delay_seconds` | `VALIDATION_DELAY_SECONDS` | `2.0` | `config.py` | 89 | Delay between sequential validations |

---

## YAML Configuration (config/models.yaml)

### Image Models

```yaml
image_models:
  - name: nano-banana-pro-edit
    provider: wavespeed
    priority: 1
    supports_greek: true
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Model identifier used in API calls |
| `provider` | string | Provider name (wavespeed) |
| `priority` | int | Processing priority (lower = higher priority) |
| `supports_greek` | bool | Whether model supports Greek text |

### Available Models (Currently Commented Out)

| Model Name | Provider | Priority | Greek Support |
|------------|----------|----------|---------------|
| `seedream-v4` | wavespeed | 1 | ✅ |
| `qwen-edit-plus` | wavespeed | 2 | ✅ |
| `wan-2.5-edit` | wavespeed | 3 | ✅ |
| `nano-banana` | wavespeed | 4 | ✅ |
| `nano-banana-pro-edit` | wavespeed | 1 | ✅ (Active) |
| `nano-banana-pro-edit-ultra` | wavespeed | 2 | ✅ |

### Enhancement Configuration

```yaml
enhancement:
  model: anthropic/claude-sonnet-4.5
  provider: openrouter
  max_tokens: 2000
  temperature: 0.7
  cache_enabled: true
```

| Field | Value | Description |
|-------|-------|-------------|
| `model` | `anthropic/claude-sonnet-4.5` | Claude model for enhancement |
| `provider` | `openrouter` | API provider |
| `max_tokens` | `2000` | Max response tokens |
| `temperature` | `0.7` | Creativity setting |
| `cache_enabled` | `true` | Enable prompt caching |

### Validation Configuration

```yaml
validation:
  model: anthropic/claude-sonnet-4.5
  provider: openrouter
  max_tokens: 1000
  temperature: 0.0
  vision_enabled: true
```

| Field | Value | Description |
|-------|-------|-------------|
| `model` | `anthropic/claude-sonnet-4.5` | Claude model for validation |
| `provider` | `openrouter` | API provider |
| `max_tokens` | `1000` | Max response tokens |
| `temperature` | `0.0` | Deterministic output |
| `vision_enabled` | `true` | Enable image analysis |

### Processing Configuration

```yaml
processing:
  max_iterations: 3
  timeout_seconds: 60
  parallel_execution: true
```

| Field | Value | Description |
|-------|-------|-------------|
| `max_iterations` | `3` | Max refinement iterations |
| `timeout_seconds` | `60` | General timeout |
| `parallel_execution` | `true` | Enable parallel processing |

### Quality Thresholds

```yaml
quality_thresholds:
  minimum_validation_score: 75
  greek_typography_accuracy: 95
  hybrid_fallback_threshold: 3
```

| Field | Value | Description |
|-------|-------|-------------|
| `minimum_validation_score` | `75` | Legacy threshold (not actively used) |
| `greek_typography_accuracy` | `95` | Greek text accuracy target |
| `hybrid_fallback_threshold` | `3` | Iterations before fallback |

---

## Hardcoded Constants

### Task Locking (webhooks.py)

| Constant | Value | File | Line | Description |
|----------|-------|------|------|-------------|
| `LOCK_TTL_SECONDS` | `3600` | `webhooks.py` | 47 | Lock timeout (1 hour) |
| `CLEANUP_CHECK_INTERVAL` | `100` | `webhooks.py` | 48 | Cleanup every N acquisitions |

### Orchestrator Defaults (orchestrator.py)

| Constant | Value | File | Line | Description |
|----------|-------|------|------|-------------|
| `max_iterations` | `3` | `orchestrator.py` | 36 | Default max iterations |
| `MAX_STEP_ATTEMPTS` | `2` | `orchestrator.py` | 61 | Default step attempts |
| `PASS_THRESHOLD` | `8` | `orchestrator.py` | 62 | Default pass threshold |

### Retry Logic (retry.py)

| Parameter | Default | File | Line | Description |
|-----------|---------|------|------|-------------|
| `max_attempts` | `3` | `retry.py` | 15 | Default retry attempts |
| `backoff_factor` | `2.0` | `retry.py` | 16 | Exponential backoff multiplier |
| `initial_delay` | `1.0` | `retry.py` | 17 | Initial retry delay (seconds) |
| `max_delay` | `60.0` | `retry.py` | 18 | Maximum retry delay (seconds) |

### OpenRouter Client (openrouter.py)

| Constant | Value | File | Line | Description |
|----------|-------|------|------|-------------|
| `base_url` | `https://openrouter.ai/api/v1` | `openrouter.py` | 43 | OpenRouter API base URL |
| `MAX_SIZE_FOR_CLAUDE` | `3.5 * 1024 * 1024` | `openrouter.py` | 417 | Max image size (3.5MB) |
| Enhancement model | `anthropic/claude-sonnet-4.5` | `openrouter.py` | 253 | Hardcoded model |
| Validation model | `anthropic/claude-sonnet-4.5` | `openrouter.py` | 522 | Hardcoded model |
| Reasoning effort | `"high"` | `openrouter.py` | 259, 527 | Claude thinking mode |

### WaveSpeed Client (wavespeed.py)

| Constant | Value | File | Line | Description |
|----------|-------|------|------|-------------|
| `base_url` | `https://api.wavespeed.ai/api/v3` | `wavespeed.py` | 28 | WaveSpeed API base URL |
| `poll_interval` | `2` | `wavespeed.py` | 224 | Polling interval (seconds) |

### Model Mapping (wavespeed.py)

```python
model_mapping = {
    "seedream-v4": "bytedance/seedream-v4/edit",
    "qwen-edit-plus": "wavespeed-ai/qwen-image/edit-plus",
    "wan-2.5-edit": "alibaba/wan-2.5/image-edit",
    "nano-banana": "google/nano-banana/edit",
    "nano-banana-pro-edit": "google/nano-banana-pro/edit",
    "nano-banana-pro-edit-ultra": "google/nano-banana-pro/edit-ultra",
}
```

### Image Processing (images.py)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_dimension` | `512` | Max dimension for context resize |
| `quality` | `70` | JPEG quality for context images |

### ClickUp Client (clickup.py)

| Constant | Value | File | Line | Description |
|----------|-------|------|------|-------------|
| `base_url` | `https://api.clickup.com/api/v2` | `clickup.py` | 28 | ClickUp API base URL |
| `timeout` | `30.0` | `clickup.py` | 17 | Default timeout |

### Brand Analyzer (brand_analyzer.py)

| Constant | Value | File | Line | Description |
|----------|-------|------|------|-------------|
| Model | `anthropic/claude-sonnet-4.5:online` | `brand_analyzer.py` | 174 | Claude with web search |
| `max_tokens` | `2000` | `brand_analyzer.py` | 176 | Response limit |
| `temperature` | `0.0` | `brand_analyzer.py` | 177 | Deterministic |
| `timeout` | `60.0` | `brand_analyzer.py` | 191 | Extended timeout for web search |

---

## File Paths

### Configuration Directories

| Path | Description | Loaded By |
|------|-------------|-----------|
| `config/` | Main config directory | `config.py` |
| `config/models.yaml` | Model definitions | `load_config()` |
| `config/prompts/` | Prompt templates | `load_validation_prompt()` |
| `config/shared/` | Shared resources | `load_fonts_guide()` |
| `config/deep_research/` | Per-model research | `load_deep_research()` |

### Prompt Files

| File | Purpose | Loaded By |
|------|---------|-----------|
| `config/prompts/validation_prompt.txt` | SIMPLE_EDIT validation | `Validator.load_validation_prompt()` |
| `config/prompts/validation_branded_creative.txt` | BRANDED_CREATIVE validation | `Validator.load_validation_prompt()` |
| `config/prompts/brand_analyzer_prompt.txt` | Brand analysis | `BrandAnalyzer._load_prompt()` |
| `config/shared/fonts.md` | Font translation guide | `load_fonts_guide()` |

### Deep Research Files (Per Model)

| File Pattern | Purpose |
|--------------|---------|
| `config/deep_research/{model}/activation.txt` | Model activation prompt |
| `config/deep_research/{model}/research.md` | Model research document |

---

## Runtime Configuration

### Orchestrator Initialization

```python
Orchestrator(
    enhancer=enhancer,
    generator=generator,
    validator=validator,
    refiner=refiner,
    hybrid_fallback=hybrid_fallback,
    max_iterations=config.max_iterations,  # From env
    config=config,  # Full config object
)
```

### Provider Initialization

```python
# OpenRouter
OpenRouterClient(
    api_key=config.openrouter_api_key,
    timeout=config.timeout_openrouter_seconds,  # Default: 120.0
)

# WaveSpeed
WaveSpeedAIClient(
    api_key=config.wavespeed_api_key,
    timeout=config.timeout_wavespeed_seconds,  # Default: 300.0
)

# ClickUp
ClickUpClient(
    api_key=config.clickup_api_key,
    timeout=30.0,  # Hardcoded
)
```

---

## Parameter Inheritance

```
Environment Variables
        ↓
    config.py (load_config)
        ↓
    Config object
        ↓
    ┌───────────────────────────────────────┐
    │                                       │
    ↓                                       ↓
Orchestrator                          Providers
    ↓                                       ↓
max_iterations                        timeouts
max_step_attempts                     rate limits
validation_pass_threshold
```

---

## Configuration Precedence

1. **Environment Variables** - Highest priority
2. **YAML Configuration** - Default values
3. **Hardcoded Defaults** - Fallback values

### Example

```python
# In config.py
max_iterations: int = Field(default=3, alias="MAX_ITERATIONS")

# Precedence:
# 1. os.environ["MAX_ITERATIONS"] if set
# 2. models.yaml max_iterations if present
# 3. default=3 if neither
```

---

## Modifying Configuration

### To Change Validation Threshold

```bash
# Environment variable
export VALIDATION_PASS_THRESHOLD=7
```

### To Add New Model

```yaml
# config/models.yaml
image_models:
  - name: new-model-name
    provider: wavespeed
    priority: 2
    supports_greek: true
```

Then add to `wavespeed.py` model_mapping:
```python
model_mapping = {
    ...
    "new-model-name": "provider/new-model/endpoint",
}
```

And create deep research files:
```
config/deep_research/new-model-name/
├── activation.txt
└── research.md
```

### To Change Timeouts

```bash
# For longer WaveSpeed operations
export TIMEOUT_WAVESPEED_SECONDS=600

# For longer Claude operations
export TIMEOUT_OPENROUTER_SECONDS=180
```

### To Adjust Rate Limits

```bash
# More concurrent enhancements
export RATE_LIMIT_ENHANCEMENT=10

# More concurrent validations
export RATE_LIMIT_VALIDATION=5
```

