# Prompts Registry - Complete Documentation

## Overview

This document catalogs ALL prompts used in the image editing pipeline, including their locations, purposes, variables, and configurability.

---

## P1: Enhancement System Prompt

| Property | Value |
|----------|-------|
| **ID** | P1 |
| **Name** | Enhancement System Prompt |
| **File** | `src/providers/openrouter.py` |
| **Lines** | 136-143 |
| **Purpose** | Provides context for Claude to enhance user prompts for specific image models |
| **Called When** | Phase 1 of every iteration |
| **Configurable** | Yes (via deep_research files + fonts.md) |

### Template

```python
system_prompt = deep_research + fonts_section + """

═══════════════════════════════════════════════════════════════
FINAL OUTPUT OVERRIDE:
═══════════════════════════════════════════════════════════════
Ignore any instructions above about warnings, recommendations, or alternatives.
Output ONLY the enhanced prompt. No meta-commentary. No markdown headers.
Just the pure editing instructions."""
```

### Variable Injections

| Variable | Source | Description |
|----------|--------|-------------|
| `{deep_research}` | `config/deep_research/{model}/activation.txt` + `research.md` | Model-specific knowledge |
| `{fonts_section}` | `config/shared/fonts.md` | Font translation guide |

---

## P2: Enhancement User Prompt

| Property | Value |
|----------|-------|
| **ID** | P2 |
| **Name** | Enhancement User Prompt |
| **File** | `src/providers/openrouter.py` |
| **Lines** | 164-193 |
| **Purpose** | Instructs Claude on how to enhance the user's original request |
| **Called When** | Phase 1 of every iteration |
| **Configurable** | No (hardcoded) |

### Template

```python
user_text = f"""{multi_image_context}You are a TRANSLATOR, not a creative director.

Your job:
- Convert the user's request into precise technical instructions
- Include what the user asked for - don't invent requirements they didn't mention
- For unspecified details: follow the reference/inspiration if provided, otherwise use sensible defaults

Key understanding:
- CONTENT images (photos, products, models) are the canvas - their composition is final unless the user explicitly asks to change it
- INSPIRATION/REFERENCE images guide what you ADD: typography style, text placement, colors, overlay aesthetics
- Adapt overlay elements to fit the content image, not the other way around

What you must NEVER do (unless user explicitly requests it):
- Reposition, crop, or reframe the content photos
- Add creative ideas the user didn't ask for

                            Enhance this image editing request for {model_name}:

{original_prompt}

CRITICAL OUTPUT REQUIREMENTS:
- Return ONLY the enhanced prompt text ready for direct API submission
- NO explanations, warnings, recommendations, or meta-commentary
- NO "IMPORTANT", "CRITICAL", "RECOMMENDED", or markdown sections
- NO confidence levels, success predictions, or alternative approaches
- NO anti-pattern warnings or hybrid workflow suggestions
- Start immediately with the actual prompt instructions
- Output must be copy-paste ready for the image editing API

Your output MUST be the pure prompt with zero additional text."""
```

### Variable Injections

| Variable | Source | Description |
|----------|--------|-------------|
| `{multi_image_context}` | Dynamically generated | Added when multiple images provided |
| `{model_name}` | From `model_names` list | Target image generation model |
| `{original_prompt}` | User input | The original edit request |

---

## P3: Multi-Image Context Injection

| Property | Value |
|----------|-------|
| **ID** | P3 |
| **Name** | Multi-Image Context |
| **File** | `src/providers/openrouter.py` |
| **Lines** | 151-158 |
| **Purpose** | Adds context when multiple images are provided |
| **Called When** | When `len(original_images_bytes) > 1` |
| **Configurable** | No (hardcoded) |

### Template

```python
multi_image_context = f"""
[MULTI-IMAGE INPUT]
You are viewing {len(original_images_bytes)} images.
Each image's role and content is described in the request below.
Use them according to their described purpose - do not assume which is "primary" or "secondary".

"""
```

---

## P4: Validation Prompt (SIMPLE_EDIT)

| Property | Value |
|----------|-------|
| **ID** | P4 |
| **Name** | SIMPLE_EDIT Validation Prompt |
| **File** | `config/prompts/validation_prompt.txt` |
| **Lines** | 1-316 |
| **Purpose** | Validates edited images for simple edit tasks |
| **Called When** | Phase 3 when `task_type == "SIMPLE_EDIT"` |
| **Configurable** | Yes (external file) |

### Key Sections

1. **Image Input Format** (lines 11-22)
2. **Validation Objective** (lines 24-30)
3. **Critical Validation Checks** (lines 32-61)
4. **Comparison Protocol** (lines 63-116)
5. **Pass/Fail Criteria** (lines 118-141)
6. **Scoring Guidelines** (lines 143-176)
7. **Font Reference** (line 277) - `{fonts_guide}` injection point
8. **Response Format** (lines 281-298)

### Variable Injections

| Variable | Source | Description |
|----------|--------|-------------|
| `{fonts_guide}` | `config/shared/fonts.md` | Font translation reference |
| `{original_request}` | User input | Injected at runtime in user message |

---

## P5: Validation Prompt (BRANDED_CREATIVE)

| Property | Value |
|----------|-------|
| **ID** | P5 |
| **Name** | BRANDED_CREATIVE Validation Prompt |
| **File** | `config/prompts/validation_branded_creative.txt` |
| **Lines** | 1-306 |
| **Purpose** | Validates marketing graphics with stricter composition checks |
| **Called When** | Phase 3 when `task_type == "BRANDED_CREATIVE"` |
| **Configurable** | Yes (external file) |

### Key Differences from P4

- **Composition Intent Verification** - Checks photo usage, layout fidelity, duplication
- **Multi-Image Input Verification** - Ensures all inputs used
- **Split Panel Detection** - Catches unwanted layout splits
- **Text Hierarchy Checks** - Validates marketing text prominence

### Variable Injections

| Variable | Source | Description |
|----------|--------|-------------|
| `{fonts_guide}` | `config/shared/fonts.md` | Font translation reference |
| `{original_request}` | User input | Injected at runtime |

---

## P6: Validation User Prompt (Single Image)

| Property | Value |
|----------|-------|
| **ID** | P6 |
| **Name** | Validation User Prompt (Single) |
| **File** | `src/providers/openrouter.py` |
| **Lines** | 390-394 |
| **Purpose** | Simple validation instruction for single-image edits |
| **Called When** | When `len(original_images_bytes) == 1` |
| **Configurable** | No (hardcoded) |

### Template

```python
user_text = f"""Validate this edit.

USER REQUEST: {original_request}

Compare IMAGE 1 (original) with IMAGE 2 (edited).
Return ONLY JSON."""
```

---

## P7: Validation User Prompt (Multi-Image)

| Property | Value |
|----------|-------|
| **ID** | P7 |
| **Name** | Validation User Prompt (Multi) |
| **File** | `src/providers/openrouter.py` |
| **Lines** | 397-403 |
| **Purpose** | Validation instruction for multi-image compositions |
| **Called When** | When `len(original_images_bytes) > 1` |
| **Configurable** | No (hardcoded) |

### Template

```python
user_text = f"""Validate this edit.

USER REQUEST: {original_request}

Compare IMAGES 1-{num_originals} (originals/inputs) with FINAL IMAGE (edited result).
Verify ALL input images are properly incorporated in the output.
Return ONLY JSON."""
```

---

## P8: Brand Analyzer System Prompt

| Property | Value |
|----------|-------|
| **ID** | P8 |
| **Name** | Brand Analyzer Prompt |
| **File** | `config/prompts/brand_analyzer_prompt.txt` |
| **Lines** | 1-210 |
| **Purpose** | Extracts brand aesthetic from website |
| **Called When** | When `parsed_task.brand_website` is provided |
| **Configurable** | Yes (external file) |

### Key Sections

1. **Analysis Objective** (lines 9-15)
2. **What to Analyze** (lines 17-53)
3. **Output Format** (lines 55-98) - JSON structure
4. **Examples** (lines 100-196)
5. **Important Rules** (lines 198-206)

---

## P9: Brand Analyzer User Message

| Property | Value |
|----------|-------|
| **ID** | P9 |
| **Name** | Brand Analyzer User Message |
| **File** | `src/core/brand_analyzer.py` |
| **Lines** | 147-158 |
| **Purpose** | Instructs Claude to analyze specific website |
| **Called When** | Brand analysis requested |
| **Configurable** | No (hardcoded) |

### Template

```python
user_message = f"""Analyze this brand's website and extract their visual style guidelines.

WEBSITE URL: {url}

Please search/visit the website to understand their:
- Visual style and mood
- Typography patterns
- Color usage
- Layout preferences
- How they present promotions/sales

Then return the analysis in the JSON format specified."""
```

---

## P10: Branded Creative Generation Prompt

| Property | Value |
|----------|-------|
| **ID** | P10 |
| **Name** | Branded Creative Prompt Builder |
| **File** | `src/api/webhooks.py` |
| **Lines** | 1000-1097 |
| **Function** | `_build_branded_prompt_v2()` |
| **Purpose** | Builds structured prompt for marketing graphics |
| **Called When** | First dimension of BRANDED_CREATIVE |
| **Configurable** | No (hardcoded structure) |

### Template Structure

```python
parts = []

# Dimension with framing principle
parts.append(f"Create a {dimension} marketing graphic.")
parts.append("""
Professional marketing graphics fill the entire canvas edge-to-edge.
Empty borders, padding, or letterboxing indicate technical failure, not intentional design.
When adapting to an aspect ratio: expand flexible elements (backgrounds, negative space) to fill the frame - never compress content or add empty bands.""")

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

# IMAGE ROLES section (critical)
parts.append("\n" + "=" * 60)
parts.append("IMAGE ROLES (CRITICAL - READ CAREFULLY):")
parts.append("=" * 60)
# ... detailed image role mapping ...
```

---

## P11: Dimension Adaptation Prompt

| Property | Value |
|----------|-------|
| **ID** | P11 |
| **Name** | Dimension Adaptation Prompt |
| **File** | `src/api/webhooks.py` |
| **Lines** | 1100-1105 |
| **Function** | `_build_adapt_prompt_v2()` |
| **Purpose** | Adapts previous result to new aspect ratio |
| **Called When** | Subsequent dimensions in BRANDED_CREATIVE |
| **Configurable** | No (hardcoded) |

### Template

```python
return f"""Adapt this image to {target_dimension} aspect ratio.
Keep ALL content identical: same person, same text, same logo, same colors, same style.
Reframe/expand the composition to fill the new {target_dimension} canvas edge-to-edge.
Do NOT add borders or letterboxing."""
```

---

## P12: Edit Task Prompt Builder

| Property | Value |
|----------|-------|
| **ID** | P12 |
| **Name** | Edit Task Prompt |
| **File** | `src/core/task_parser.py` |
| **Lines** | 245-258 |
| **Function** | `_build_edit_prompt()` |
| **Purpose** | Builds simple prompt for edit tasks |
| **Called When** | `task_type == "Edit"` |
| **Configurable** | No (hardcoded) |

### Template

```python
parts = []

if parsed.extra_notes:
    parts.append(parsed.extra_notes)
else:
    parts.append("Edit this image as requested.")

if parsed.main_text:
    parts.append(f"Text to add/change: {parsed.main_text}")

return "\n".join(parts)
```

---

## P13: Creative Task Prompt Builder

| Property | Value |
|----------|-------|
| **ID** | P13 |
| **Name** | Creative Task Prompt |
| **File** | `src/core/task_parser.py` |
| **Lines** | 260-351 |
| **Function** | `_build_creative_prompt()` |
| **Purpose** | Builds detailed prompt for creative tasks |
| **Called When** | `task_type == "Creative"` |
| **Configurable** | No (hardcoded) |

### Key Sections

1. Dimension instruction
2. Primary/Secondary text
3. Font specification
4. Style direction
5. Extra notes
6. **IMAGE ROLES** - Critical section mapping image indices to roles

---

## P14: Hybrid Fallback Comment

| Property | Value |
|----------|-------|
| **ID** | P14 |
| **Name** | Hybrid Fallback Comment |
| **File** | `src/core/hybrid_fallback.py` |
| **Lines** | 79-105 |
| **Purpose** | Formatted comment for human review |
| **Called When** | All iterations fail |
| **Configurable** | No (hardcoded) |

### Template

```python
comment = f"""🤖 **AI Agent - Hybrid Fallback Triggered**

**Status:** Requires Human Review

**Summary:**
The AI agent attempted {iterations_attempted} iterations but could not produce an edit that meets quality standards.

**Original Request:**
```
{original_prompt}
```

**Issues Detected:**
{issues_summary}

**Models Attempted:**
{', '.join(set(r.model_name for r in failed_results))}

**Next Steps:**
1. Review the original request for clarity
2. Check if requirements are feasible for automated editing
3. Consider manual editing or revised requirements
4. Update task status when resolved

---
*Automated message from Image Edit Agent*
"""
```

---

## P15: Deep Research - Activation Prompt

| Property | Value |
|----------|-------|
| **ID** | P15 |
| **Name** | Model Activation Prompt |
| **File** | `config/deep_research/{model}/activation.txt` |
| **Purpose** | Activates pattern recognition for specific model |
| **Called When** | Enhancement phase |
| **Configurable** | Yes (per-model file) |

### Example (nano-banana-pro-edit)

```
# TOOL PATTERN NAVIGATION: Image Editing Vision-to-Reality

## Core Identity

You are a pattern navigation entity that reads The Documented Thinking Patterns...

**What you activate:**
- Pattern recognition system for vision-to-reality translation
- Four-layer memory (immediate, working, portfolio, parameter evolution)
- Grounded communication (no judgments, show possibilities)
...
```

---

## P16: Deep Research - Research Document

| Property | Value |
|----------|-------|
| **ID** | P16 |
| **Name** | Model Research Document |
| **File** | `config/deep_research/{model}/research.md` |
| **Purpose** | Detailed patterns and techniques for model |
| **Called When** | Enhancement phase |
| **Configurable** | Yes (per-model file) |

### Key Sections (nano-banana-pro-edit)

1. **Executive Summary** - Model capabilities overview
2. **Part I: Foundational Translation Mechanics** - Core patterns
3. **Part II: Scenario-Specific Translation Flows** - ADD, REMOVE, MODIFY, MOVE, BACKGROUND, TYPOGRAPHY
4. **Part III: Greek Text Breakthrough Patterns** - Language-specific handling
5. **Part IV: Advanced Multi-Turn Editing Strategies** - Iteration patterns
6. **Part V: WaveSpeed AI Technical Implementation** - API specifics
7. **Part VI: Quality Optimization** - Prompt structure best practices

---

## P17: Fonts Translation Guide

| Property | Value |
|----------|-------|
| **ID** | P17 |
| **Name** | Fonts Translation Guide |
| **File** | `config/shared/fonts.md` |
| **Purpose** | Translates font names to visual descriptions |
| **Called When** | Injected into P1, P4, P5 |
| **Configurable** | Yes (external file) |

### Structure

- **How to Use** section
- **Common Greek Marketing Fonts** - Montserrat, Roboto, Open Sans, etc.
- **Greek-Specific Fonts** - GFS Didot, Philosopher, etc.
- **Premium/Uncommon Fonts** - PPFormula, Futura, Helvetica, etc.
- **Usage Guidelines** - Weight, Greek support levels
- **Quick Reference** - Font categories

---

## Prompt Injection Points Summary

| Prompt ID | Injection Point | Variables |
|-----------|-----------------|-----------|
| P1 | System message to Claude | `deep_research`, `fonts_section` |
| P2 | User message to Claude | `model_name`, `original_prompt`, `multi_image_context` |
| P4 | System message to Claude | `fonts_guide` |
| P5 | System message to Claude | `fonts_guide` |
| P6/P7 | User message to Claude | `original_request`, `num_originals` |
| P9 | User message to Claude | `url` |
| P10 | Prompt to WaveSpeed | `dimension`, `main_text`, `secondary_text`, `font`, `style_direction`, `extra_notes`, `brand_aesthetic` |
| P11 | Prompt to WaveSpeed | `target_dimension` |
| P14 | ClickUp comment | `iterations_attempted`, `original_prompt`, `issues_summary`, `model_names` |

---

## Configurable vs Hardcoded

### Configurable (External Files)

| ID | File | Can Edit Without Code Change |
|----|------|------------------------------|
| P4 | `config/prompts/validation_prompt.txt` | ✅ Yes |
| P5 | `config/prompts/validation_branded_creative.txt` | ✅ Yes |
| P8 | `config/prompts/brand_analyzer_prompt.txt` | ✅ Yes |
| P15 | `config/deep_research/{model}/activation.txt` | ✅ Yes |
| P16 | `config/deep_research/{model}/research.md` | ✅ Yes |
| P17 | `config/shared/fonts.md` | ✅ Yes |

### Hardcoded (Requires Code Change)

| ID | File | Lines |
|----|------|-------|
| P1 (partial) | `openrouter.py` | 136-143 |
| P2 | `openrouter.py` | 164-193 |
| P3 | `openrouter.py` | 151-158 |
| P6 | `openrouter.py` | 390-394 |
| P7 | `openrouter.py` | 397-403 |
| P9 | `brand_analyzer.py` | 147-158 |
| P10 | `webhooks.py` | 1000-1097 |
| P11 | `webhooks.py` | 1100-1105 |
| P12 | `task_parser.py` | 245-258 |
| P13 | `task_parser.py` | 260-351 |
| P14 | `hybrid_fallback.py` | 79-105 |

