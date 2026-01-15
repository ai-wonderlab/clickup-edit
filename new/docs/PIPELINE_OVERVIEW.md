# Image Editing Pipeline - Complete Overview

## Executive Summary

This document provides a comprehensive overview of the ClickUp-integrated AI image editing pipeline. The system processes image editing requests from ClickUp tasks, using Claude Sonnet 4.5 for prompt enhancement and validation, and WaveSpeed AI (nano-banana-pro-edit) for image generation.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLICKUP WEBHOOK                                │
│                         (Entry Point)                                    │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         TASK VALIDATION                                  │
│  • Signature verification                                                │
│  • Lock acquisition                                                      │
│  • Status check (must be "to do")                                       │
│  • AI Edit checkbox check                                               │
│  • Custom field parsing (TaskParser)                                    │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
                    ▼                         ▼
         ┌─────────────────┐       ┌─────────────────┐
         │   SIMPLE_EDIT   │       │BRANDED_CREATIVE │
         │                 │       │                 │
         │ Single image    │       │ Multiple images │
         │ Simple prompt   │       │ Dimension loop  │
         │ Basic validation│       │ Brand analysis  │
         └────────┬────────┘       └────────┬────────┘
                  │                         │
                  └───────────┬─────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR                                     │
│                    (Main Processing Loop)                                │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    ITERATION LOOP (max 3)                        │    │
│  │                                                                  │    │
│  │  PHASE 1: Enhancement                                           │    │
│  │    └─ Claude Sonnet 4.5 + Deep Research + Fonts Guide           │    │
│  │                                                                  │    │
│  │  PHASE 2: Generation                                            │    │
│  │    └─ WaveSpeed API (nano-banana-pro-edit)                      │    │
│  │                                                                  │    │
│  │  PHASE 3: Validation                                            │    │
│  │    └─ Claude Sonnet 4.5 + Validation Prompt                     │    │
│  │                                                                  │    │
│  │  PHASE 4: Decision                                              │    │
│  │    └─ Score >= 8? → SUCCESS                                     │    │
│  │    └─ Score < 8? → Refine or Sequential                         │    │
│  │                                                                  │    │
│  │  PHASE 5: Refinement (if needed)                                │    │
│  │    └─ Aggregate feedback, re-enhance, regenerate                │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    SEQUENTIAL MODE                               │    │
│  │  (After 3 failed iterations)                                    │    │
│  │                                                                  │    │
│  │  • Parse request into atomic steps                              │    │
│  │  • Execute each step with full pipeline                         │    │
│  │  • Use previous output as next input                            │    │
│  │  • 2 attempts per step                                          │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    HYBRID FALLBACK                               │    │
│  │  (If all else fails)                                            │    │
│  │                                                                  │    │
│  │  • Update ClickUp status to "blocked"                           │    │
│  │  • Add detailed comment with issues                             │    │
│  │  • Trigger human review                                         │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         SUCCESS PATH                                     │
│  • Upload final image to ClickUp                                        │
│  • Update status to "complete"                                          │
│  • Add success comment                                                  │
│  • Uncheck AI Edit checkbox                                             │
│  • Release task lock                                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Key Components

### 1. Entry Point (`src/api/webhooks.py`)

- Handles ClickUp webhook events
- Implements per-task locking with TTL
- Parses custom fields via `TaskParser`
- Routes to SIMPLE_EDIT or BRANDED_CREATIVE flow

### 2. Orchestrator (`src/core/orchestrator.py`)

- Coordinates the entire workflow
- Manages iteration loop (max 3)
- Handles sequential mode fallback
- Triggers hybrid fallback when needed

### 3. Prompt Enhancer (`src/core/prompt_enhancer.py`)

- Enhances user prompts for image models
- Loads deep research per model
- Injects fonts guide
- Uses Claude Sonnet 4.5 with thinking mode

### 4. Image Generator (`src/core/image_generator.py`)

- Generates images via WaveSpeed API
- Supports multiple models (currently nano-banana-pro-edit)
- Handles multi-image input
- Supports aspect ratio specification

### 5. Validator (`src/core/validator.py`)

- Validates generated images
- Uses task-type-specific prompts
- Compares original vs edited images
- Returns score (0-10) and issues

### 6. Refiner (`src/core/refiner.py`)

- Aggregates feedback from failures
- Implements sequential mode
- Breaks complex requests into steps
- Re-runs pipeline with clean prompts

### 7. Hybrid Fallback (`src/core/hybrid_fallback.py`)

- Triggers human review
- Updates ClickUp with detailed issues
- Sets task to "blocked" status

---

## API Integrations

| Provider | Purpose | Model/Endpoint |
|----------|---------|----------------|
| **OpenRouter** | Enhancement & Validation | `anthropic/claude-sonnet-4.5` |
| **WaveSpeed** | Image Generation | `google/nano-banana-pro/edit` |
| **ClickUp** | Task Management | v2 API |

---

## Configuration Files

| File | Purpose |
|------|---------|
| `config/models.yaml` | Model definitions, thresholds |
| `config/prompts/validation_prompt.txt` | SIMPLE_EDIT validation |
| `config/prompts/validation_branded_creative.txt` | BRANDED_CREATIVE validation |
| `config/prompts/brand_analyzer_prompt.txt` | Brand website analysis |
| `config/shared/fonts.md` | Font translation guide |
| `config/deep_research/{model}/` | Per-model activation + research |

---

## Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_iterations` | 3 | Max refinement iterations |
| `validation_pass_threshold` | 8 | Minimum score to pass |
| `max_step_attempts` | 2 | Attempts per sequential step |
| `timeout_openrouter_seconds` | 120 | Claude API timeout |
| `timeout_wavespeed_seconds` | 300 | WaveSpeed API timeout |
| `validation_delay_seconds` | 2 | Delay between validations |

---

## Task Types

### SIMPLE_EDIT

- Single image input
- Simple edit instructions
- Uses `validation_prompt.txt`
- Direct iteration loop

### BRANDED_CREATIVE

- Multiple images (main, additional, logo, reference)
- Text content (main, secondary)
- Font and style specifications
- Dimension loop (multiple aspect ratios)
- Uses `validation_branded_creative.txt`
- Optional brand website analysis

---

## Prompt Flow

```
User Request
    │
    ▼
┌─────────────────────────────────────┐
│ TaskParser.build_prompt()           │
│ - Extracts from custom fields       │
│ - Adds image role mapping           │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│ PromptEnhancer.enhance_single()     │
│ System: Deep Research + Fonts       │
│ User: Enhancement instructions      │
│ + Images (iteration 1 only)         │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│ WaveSpeed API                       │
│ - Enhanced prompt                   │
│ - Image URLs                        │
│ - Aspect ratio (optional)           │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│ Validator.validate_single()         │
│ System: Validation prompt           │
│ User: Original request + images     │
│ Returns: JSON {pass_fail, score}    │
└─────────────────────────────────────┘
```

---

## Documentation Index

| Document | Contents |
|----------|----------|
| [flow_diagram.md](./flow_diagram.md) | Complete Mermaid diagrams |
| [prompts_registry.md](./prompts_registry.md) | All prompts with locations |
| [config_registry.md](./config_registry.md) | All configurable parameters |
| [api_calls.md](./api_calls.md) | All API payloads |
| [decision_points.md](./decision_points.md) | All conditionals |

---

## Quick Reference

### To modify validation behavior:
1. Edit `config/prompts/validation_prompt.txt` or `validation_branded_creative.txt`
2. Adjust `VALIDATION_PASS_THRESHOLD` environment variable

### To add a new model:
1. Add to `config/models.yaml`
2. Add endpoint to `wavespeed.py` model_mapping
3. Create `config/deep_research/{model}/activation.txt` and `research.md`

### To change iteration limits:
1. Set `MAX_ITERATIONS` environment variable
2. Set `MAX_STEP_ATTEMPTS` for sequential mode

### To adjust timeouts:
1. Set `TIMEOUT_OPENROUTER_SECONDS` for Claude
2. Set `TIMEOUT_WAVESPEED_SECONDS` for image generation

---

## Version Info

- **Claude Model**: `anthropic/claude-sonnet-4.5`
- **Image Model**: `nano-banana-pro-edit` (Google Nano Banana Pro)
- **Reasoning Mode**: High effort (thinking enabled)
- **Provider Lock**: Anthropic only (no fallbacks)

