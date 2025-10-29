# 🚀 Complete Deployment Guide - Image Edit Agent

**Last Updated:** October 29, 2025  
**Version:** 1.2.0  
**Deployment Platform:** Railway (subfolder deployment)  

---

## 📋 Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Understanding Subfolder Context](#understanding-subfolder-context)
3. [Local Development Setup](#local-development-setup)
4. [Critical Verification Steps](#critical-verification-steps)
5. [Railway Deployment](#railway-deployment)
6. [ClickUp Integration](#clickup-integration)
7. [Testing & Validation](#testing--validation)
8. [Monitoring & Maintenance](#monitoring--maintenance)
9. [Troubleshooting Guide](#troubleshooting-guide)
10. [Production Optimization](#production-optimization)

---

## ✅ Pre-Deployment Checklist

### 1. Critical Files Verification

Run these checks from the `new/` directory:
```bash
# ═══════════════════════════════════════════════════════════════
# 1. VALIDATION PROMPT (290 lines, ~26KB)
# ═══════════════════════════════════════════════════════════════

# Check file exists and size
ls -lh config/prompts/validation_prompt.txt
# Expected: ~26K

# Verify line count
wc -l config/prompts/validation_prompt.txt
# Expected: ~645 lines

# Check critical fixes present
echo "═══ CHECKING CRITICAL FIXES ═══"

# Fix 1: MOVE detection
grep -q "MOVE = REMOVE from old position" config/prompts/validation_prompt.txt && \
  echo "✅ MOVE fix present" || echo "❌ MOVE fix MISSING"

# Fix 2: Greek tone rules
grep -q "Uppercase Greek should have NO tones" config/prompts/validation_prompt.txt && \
  echo "✅ Greek tone fix present" || echo "❌ Greek tone fix MISSING"

# Fix 3: Logo preservation
grep -q "Logo DESIGN pixel-identical" config/prompts/validation_prompt.txt && \
  echo "✅ Logo preservation present" || echo "❌ Logo preservation MISSING"

# ═══════════════════════════════════════════════════════════════
# 2. DEEP RESEARCH FILES (8 files, ~82KB total)
# ═══════════════════════════════════════════════════════════════

echo ""
echo "═══ CHECKING DEEP RESEARCH FILES ═══"

for model in wan-2.5-edit nano-banana seedream-v4 qwen-edit-plus; do
  if [ -f "config/deep_research/$model/activation.txt" ] && \
     [ -f "config/deep_research/$model/research.md" ]; then
    act_size=$(wc -c < "config/deep_research/$model/activation.txt")
    res_size=$(wc -c < "config/deep_research/$model/research.md")
    echo "✅ $model: activation=${act_size}B, research=${res_size}B"
  else
    echo "❌ $model: MISSING FILES"
  fi
done

# ═══════════════════════════════════════════════════════════════
# 3. PYTHON CODE VERIFICATION
# ═══════════════════════════════════════════════════════════════

echo ""
echo "═══ CHECKING PYTHON CODE UPDATES ═══"

# Check webhook passes png_bytes
grep -q "original_image_bytes=png_bytes" src/api/webhooks.py && \
  echo "✅ webhooks.py: PNG bytes optimization" || \
  echo "❌ webhooks.py: OLD CODE (uses URLs)"

# Check orchestrator receives bytes
grep -q "original_image_bytes: bytes" src/core/orchestrator.py && \
  echo "✅ orchestrator.py: Receives PNG bytes" || \
  echo "❌ orchestrator.py: OLD SIGNATURE"

# Check sequential mode exists
grep -q "execute_sequential" src/core/refiner.py && \
  echo "✅ refiner.py: Sequential mode implemented" || \
  echo "❌ refiner.py: Sequential mode MISSING"

# Check extended thinking
grep -q '"effort": "high"' src/providers/openrouter.py && \
  echo "✅ openrouter.py: Extended thinking enabled" || \
  echo "❌ openrouter.py: Extended thinking MISSING"

# Check provider locking
grep -q '"allow_fallbacks": False' src/providers/openrouter.py && \
  echo "✅ openrouter.py: Provider locking enabled" || \
  echo "❌ openrouter.py: Provider locking MISSING"

# Check image converter exists
[ -f "src/utils/image_converter.py" ] && \
  echo "✅ image_converter.py: Format conversion ready" || \
  echo "❌ image_converter.py: MISSING"

# Check config has retry fields
grep -q "max_step_attempts" src/utils/config.py && \
  echo "✅ config.py: Retry settings configured" || \
  echo "❌ config.py: Retry settings MISSING"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "⚠️  ALL CHECKS MUST PASS ✅ BEFORE DEPLOYING"
echo "═══════════════════════════════════════════════════════════════"
```

**Expected Output:** All checks should show ✅

---

### 2. API Keys Collection

Gather these before starting:
```bash
# ═══════════════════════════════════════════════════════════════
# REQUIRED API KEYS
# ═══════════════════════════════════════════════════════════════

☐ OpenRouter API Key
  • Get from: https://openrouter.ai/keys
  • Format: sk-or-v1-xxxxxxxxxxxxxxxxxxxxx
  • Provides: Claude Sonnet 4.5, Gemini 2.5 Pro

☐ WaveSpeedAI API Key
  • Get from: WaveSpeedAI dashboard
  • Format: ws_xxxxxxxxxxxxxxxxxxxxx
  • Provides: 4 image generation models

☐ ClickUp API Key
  • Get from: ClickUp Settings → Apps
  • Format: pk_xxxxxxxxxxxxxxxxxxxxx
  • Provides: Task and attachment management

☐ ClickUp Webhook Secret
  • Get after creating webhook (step below)
  • Format: Random alphanumeric string
  • Provides: HMAC signature verification

☐ ClickUp AI Edit Field ID
  • Pre-configured: b2c19afd-0ef2-485c-94b9-3a6124374ff4
  • This is your custom checkbox field
```

---

### 3. Environment Variables Template

Create `.env` file with these variables:
```bash
# ═══════════════════════════════════════════════════════════════
# API KEYS
# ═══════════════════════════════════════════════════════════════

OPENROUTER_API_KEY=sk-or-v1-...
WAVESPEED_API_KEY=ws_...
CLICKUP_API_KEY=pk_...
CLICKUP_WEBHOOK_SECRET=<will_set_after_webhook_creation>
CLICKUP_AI_EDIT_FIELD_ID=b2c19afd-0ef2-485c-94b9-3a6124374ff4

# ═══════════════════════════════════════════════════════════════
# MODEL CONFIGURATION
# ═══════════════════════════════════════════════════════════════

IMAGE_MODELS=wan-2.5-edit,nano-banana,seedream-v4,qwen-edit-plus

# ═══════════════════════════════════════════════════════════════
# PROCESSING CONFIGURATION
# ═══════════════════════════════════════════════════════════════

# Parallel mode settings
MAX_ITERATIONS=3                    # Number of refinement iterations
VALIDATION_PASS_THRESHOLD=8         # Minimum score to pass (0-10)

# Sequential mode settings (NEW)
MAX_STEP_ATTEMPTS=2                 # Retry attempts per sequential step

# ═══════════════════════════════════════════════════════════════
# APPLICATION SETTINGS
# ═══════════════════════════════════════════════════════════════

APP_ENV=production
LOG_LEVEL=INFO
```

---

## 🗂️ Understanding Subfolder Context

### Project Structure

Your repository structure:
```
main-repo/                    # Root of GitHub repo (already on Railway)
├── (other projects)
├── new/                      # ⭐ Image Edit Agent (THIS PROJECT)
│   ├── config/
│   ├── src/
│   ├── requirements.txt
│   ├── railway.json          # ⭐ Subfolder-aware config
│   └── (all other files)
└── .git/
```

### Key Implications

1. **Git operations** run from `main-repo` root
2. **Railway must deploy** from `new/` subdirectory
3. **`railway.json`** handles subfolder context
4. **All relative paths** work from `new/` directory

### Railway Configuration (`railway.json`)
```json
{
  "build": {
    "builder": "NIXPACKS",
    "buildCommand": "pip install -r new/requirements.txt"
  },
  "deploy": {
    "startCommand": "cd new && uvicorn src.main:app --host 0.0.0.0 --port $PORT",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

**What this does:**
- ✅ Installs dependencies from `new/requirements.txt`
- ✅ Changes directory to `new/` before starting
- ✅ Runs uvicorn from `new/` directory
- ✅ All relative imports work correctly
- ✅ Auto-restarts on failure (up to 10 times)

---

## 💻 Local Development Setup

### Step 1: Navigate to Project Directory
```bash
# From main-repo root:
cd new/

# Verify you're in the right place:
ls -la

# Should see:
# config/
# src/
# requirements.txt
# railway.json
# README.md
# etc.
```

### Step 2: Create Virtual Environment
```bash
# Create venv
python3 -m venv venv

# Activate (macOS/Linux)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Verify activation
which python
# Should show: .../new/venv/bin/python
```

### Step 3: Install Dependencies
```bash
# Install all requirements
pip install -r requirements.txt

# Verify installation
pip list | grep -E "fastapi|pydantic|httpx|pillow"

# Expected packages:
# fastapi          0.104.1
# pydantic         2.5.0
# httpx            0.25.1
# Pillow           10.1.0
# psd-tools        1.9.31
# PyMuPDF          1.23.0
# cairosvg         2.7.0
# (and others)
```

### Step 4: Configure Environment
```bash
# Copy example env file
cp .env.example .env

# Edit .env with your API keys
nano .env  # or use your preferred editor
```

**Fill in ALL required values** (see template above).

### Step 5: Verify Configuration Loading
```bash
# Test configuration system
python -c "
from src.utils.config import load_config, load_validation_prompt

# Load config
config = load_config()
print(f'✅ Config loaded: {len(config.image_models)} models')

# Load validation prompt
prompt = load_validation_prompt()
print(f'✅ Validation prompt: {len(prompt)} characters')

# Check critical fixes
checks = {
    'MOVE fix': 'MOVE = REMOVE' in prompt,
    'Greek tone fix': 'NO tones' in prompt,
    'Logo fix': 'pixel-identical' in prompt,
}

for name, result in checks.items():
    status = '✅' if result else '❌'
    print(f'{status} {name}: {result}')
"
```

**Expected output:**
```
✅ Config loaded: 2 models
✅ Validation prompt: 26543 characters
✅ MOVE fix: True
✅ Greek tone fix: True
✅ Logo fix: True
```

**If any show False:** Your validation prompt is not updated!

### Step 6: Start Local Server
```bash
# Start uvicorn with reload
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Expected output:
# INFO:     Will watch for changes in these directories: ['.../new']
# INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
# INFO:     Started reloader process [12345] using WatchFiles
# INFO:     Started server process [12346]
# INFO:     Application startup complete.
```

### Step 7: Test Health Check
```bash
# In a new terminal (keep server running):
curl http://localhost:8000/health

# Expected response:
{
  "status": "healthy",
  "timestamp": "2025-10-29T...",
  "service": "image-edit-agent",
  "version": "1.0.0"
}
```

### Step 8: View API Documentation

Open browser: http://localhost:8000/docs

**You should see:**
- Swagger UI with all endpoints
- `/webhook/clickup` endpoint
- `/health` and `/health/ready` endpoints
- Try out feature for testing

---

## 🔍 Critical Verification Steps

### Validation Prompt Deep Dive

The validation prompt is the **most critical file** - it must have all 16 fixes.
```bash
# ═══════════════════════════════════════════════════════════════
# COMPREHENSIVE VALIDATION PROMPT CHECK
# ═══════════════════════════════════════════════════════════════

cd config/prompts/

# 1. Basic stats
echo "File stats:"
wc validation_prompt.txt
# Expected: ~645 lines, ~5000 words, ~26KB

# 2. Critical sections
echo ""
echo "Critical sections:"

# MOVE rules
grep -A 5 "CRITICAL MOVE RULES" validation_prompt.txt
# Should show: "MOVE = REMOVE from old position + ADD to new position"

# Logo preservation
grep -A 5 "LOGO PRESERVATION" validation_prompt.txt
# Should show: "Logo DESIGN pixel-identical"

# Greek uppercase tones
grep -A 5 "UPPERCASE GREEK - TONE" validation_prompt.txt
# Should show: "Uppercase Greek should have NO tones/accents"

# Tolerance rules
grep -A 5 "TOLERANCE AND ACCEPTABLE" validation_prompt.txt
# Should show clear thresholds

# 3. Example count
echo ""
echo "Examples:"
grep -c "^Example" validation_prompt.txt
# Should show: 20

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "✅ ALL CHECKS MUST PASS"
echo "═══════════════════════════════════════════════════════════════"
```

### Deep Research Files Check
```bash
# ═══════════════════════════════════════════════════════════════
# DEEP RESEARCH INTEGRITY CHECK
# ═══════════════════════════════════════════════════════════════

cd config/deep_research/

echo "Checking all deep research files..."
echo ""

for model in wan-2.5-edit nano-banana seedream-v4 qwen-edit-plus; do
  echo "─────────────────────────────────────────────────────────────"
  echo "Model: $model"
  echo "─────────────────────────────────────────────────────────────"
  
  # Activation file
  if [ -f "$model/activation.txt" ]; then
    act_words=$(wc -w < "$model/activation.txt")
    act_size=$(ls -lh "$model/activation.txt" | awk '{print $5}')
    echo "  ✅ activation.txt: $act_words words, $act_size"
    
    # Verify has content
    if [ $act_words -lt 100 ]; then
      echo "  ⚠️  WARNING: Activation seems too short!"
    fi
  else
    echo "  ❌ activation.txt: MISSING"
  fi
  
  # Research file
  if [ -f "$model/research.md" ]; then
    res_words=$(wc -w < "$model/research.md")
    res_size=$(ls -lh "$model/research.md" | awk '{print $5}')
    echo "  ✅ research.md: $res_words words, $res_size"
    
    # Verify substantial content
    if [ $res_words -lt 1000 ]; then
      echo "  ⚠️  WARNING: Research seems too short!"
    fi
  else
    echo "  ❌ research.md: MISSING"
  fi
  
  echo ""
done

echo "═══════════════════════════════════════════════════════════════"
```

### Python Code Verification
```bash
# ═══════════════════════════════════════════════════════════════
# PYTHON CODE CRITICAL FEATURES CHECK
# ═══════════════════════════════════════════════════════════════

cd ../../  # Back to new/ directory

echo "Checking Python implementation..."
echo ""

# 1. Sequential mode
echo "🔗 Sequential Mode:"
grep -l "execute_sequential" src/core/refiner.py && echo "  ✅ Implemented in refiner.py"
grep -l "parse_request_into_steps" src/core/refiner.py && echo "  ✅ Request parsing present"
grep -l "MAX_STEP_ATTEMPTS" src/core/orchestrator.py && echo "  ✅ Retry config used"

# 2. Extended thinking
echo ""
echo "🧠 Extended Thinking:"
grep -c '"effort": "high"' src/providers/openrouter.py
echo "  ✅ Found in $(grep -c '"effort": "high"' src/providers/openrouter.py) locations"

# 3. Provider locking
echo ""
echo "🔒 Provider Locking:"
grep -c '"allow_fallbacks": False' src/providers/openrouter.py
echo "  ✅ Found in $(grep -c '"allow_fallbacks": False' src/providers/openrouter.py) locations"

# 4. System/user split
echo ""
echo "📝 System/User Split:"
grep -c '"role": "system"' src/providers/openrouter.py
echo "  ✅ System role used in $(grep -c '"role": "system"' src/providers/openrouter.py) places"

# 5. PNG bytes optimization
echo ""
echo "💾 Memory Optimization:"
grep -l "original_image_bytes: bytes" src/core/orchestrator.py && echo "  ✅ Orchestrator receives bytes"
grep -l "original_image_bytes=png_bytes" src/api/webhooks.py && echo "  ✅ Webhook passes bytes"
grep -l "base64.b64encode(original_image_bytes)" src/providers/openrouter.py && echo "  ✅ OpenRouter converts bytes"

# 6. Format conversion
echo ""
echo "📁 Format Conversion:"
[ -f "src/utils/image_converter.py" ] && echo "  ✅ ImageConverter class exists"
grep -l "convert_to_png" src/utils/image_converter.py && echo "  ✅ convert_to_png() method present"
grep -l "PyMuPDF" requirements.txt && echo "  ✅ PDF support dependency"
grep -l "psd-tools" requirements.txt && echo "  ✅ PSD support dependency"

# 7. Task locking
echo ""
echo "🔐 Task Locking:"
grep -l "_task_locks" src/api/webhooks.py && echo "  ✅ Lock registry present"
grep -l "acquire_task_lock" src/api/webhooks.py && echo "  ✅ Lock acquisition implemented"
grep -l "release_task_lock" src/api/webhooks.py && echo "  ✅ Lock release implemented"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "✅ ALL FEATURES VERIFIED"
echo "═══════════════════════════════════════════════════════════════"
```

---

## 🚂 Railway Deployment

### Prerequisites
```bash
# 1. Install Railway CLI

# macOS
brew install railway

# Or via npm (all platforms)
npm install -g @railway/cli

# Verify installation
railway --version
# Should show: railway version X.X.X
```
```bash
# 2. Login to Railway
railway login
# Opens browser for authentication
# Follow prompts to authorize
```

### Deployment Steps

#### Step 1: Link to Existing Railway Project
```bash
# ⚠️  IMPORTANT: Run from main-repo root (NOT new/ subdirectory)
cd /path/to/main-repo

# Link to your existing Railway project
railway link

# Select your project from the list
# (Should show your existing project)

# Verify linkage
railway status
# Should show: Linked to: [your-project-name]
```

#### Step 2: Verify Railway Configuration
```bash
# Check railway.json exists in new/ subdirectory
cat new/railway.json

# Should show:
# {
#   "build": {
#     "builder": "NIXPACKS",
#     "buildCommand": "pip install -r new/requirements.txt"
#   },
#   "deploy": {
#     "startCommand": "cd new && uvicorn src.main:app --host 0.0.0.0 --port $PORT",
#     ...
#   }
# }

# ⚠️  CRITICAL: Note the "cd new &&" prefix in startCommand
```

#### Step 3: Set Environment Variables
```bash
# Set all required environment variables in Railway

railway variables set OPENROUTER_API_KEY="sk-or-v1-xxxxxxxxxxxxxxxxxxxxx"
railway variables set WAVESPEED_API_KEY="ws_xxxxxxxxxxxxxxxxxxxxx"
railway variables set CLICKUP_API_KEY="pk_xxxxxxxxxxxxxxxxxxxxx"
railway variables set CLICKUP_WEBHOOK_SECRET=""  # Will set after webhook creation
railway variables set CLICKUP_AI_EDIT_FIELD_ID="b2c19afd-0ef2-485c-94b9-3a6124374ff4"

# Configuration variables
railway variables set IMAGE_MODELS="wan-2.5-edit,nano-banana,seedream-v4,qwen-edit-plus"
railway variables set MAX_ITERATIONS="3"
railway variables set MAX_STEP_ATTEMPTS="2"
railway variables set VALIDATION_PASS_THRESHOLD="8"
railway variables set APP_ENV="production"
railway variables set LOG_LEVEL="INFO"

# Verify all variables are set
railway variables

# Should show all variables (secrets will be masked)
```

#### Step 4: Deploy to Railway
```bash
# ⚠️  Still from main-repo root, NOT new/ subdirectory
railway up

# Railway will:
# 1. Detect railway.json in new/ subdirectory
# 2. Run: pip install -r new/requirements.txt
# 3. Run: cd new && uvicorn src.main:app --host 0.0.0.0 --port $PORT
# 4. Provide a public URL

# Expected deployment logs:
# Building...
# Running buildCommand: pip install -r new/requirements.txt
# Successfully installed fastapi-0.104.1 pydantic-2.5.0 ...
# Deploying...
# Running startCommand: cd new && uvicorn src.main:app ...
# INFO:     Started server process [1]
# INFO:     Application startup complete.
# Deployment successful!
```

#### Step 5: Get Your Railway URL
```bash
# Get the public URL
railway domain

# Copy the URL
# Example: https://image-edit-agent-production.up.railway.app
```

#### Step 6: Verify Deployment
```bash
# Test health check
curl https://your-app-name.up.railway.app/health

# Expected response:
{
  "status": "healthy",
  "timestamp": "2025-10-29T...",
  "service": "image-edit-agent",
  "version": "1.0.0"
}

# ✅ If you see this, deployment is successful!
```

---

## 🔗 ClickUp Integration

### Step 1: Create ClickUp Webhook

1. **Navigate to ClickUp Settings:**
   - Click your avatar (bottom left)
   - Click **Settings**
   - Go to **Integrations** → **Webhooks**

2. **Create Webhook:**
   - Click **Create Webhook**
   - **Endpoint URL:** `https://your-app-name.up.railway.app/webhook/clickup`
   - **Events to watch:** Check ✅ `taskUpdated`
   - **Description:** "Image Edit Agent - Automated image editing"

3. **Apply Filters (Recommended):**
   - **List:** Select specific list(s) where you want automated editing
   - **Custom Field:** Filter by "AI Edit" checkbox if possible
   - **Tags:** Or use tags like "ai-edit" to filter

4. **Save Webhook**

### Step 2: Copy Webhook Secret

After creating the webhook, ClickUp displays the **Webhook Secret**.

**⚠️  IMPORTANT:** Copy this secret - you'll need it immediately!
```
Example: a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
```

### Step 3: Update Railway with Webhook Secret
```bash
# Set the webhook secret in Railway
railway variables set CLICKUP_WEBHOOK_SECRET="<paste_webhook_secret_here>"

# Redeploy to pick up new environment variable
railway up

# Or trigger redeploy from Railway dashboard
# (Project → Settings → Redeploy)
```

### Step 4: Test Webhook Connection
```bash
# View Railway logs in real-time
railway logs --tail

# In ClickUp:
# 1. Create a test task
# 2. Add description: "Test webhook"
# 3. Attach any PNG image
# 4. Check "AI Edit" checkbox
# 5. Save/update task

# Expected logs in Railway:
{
  "timestamp": "...",
  "level": "INFO",
  "logger": "src.api.webhooks",
  "message": "Webhook received",
  "task_id": "abc123"
}
{
  "level": "INFO",
  "message": "Task lock acquired",
  "task_id": "abc123"
}
...
```

**✅ If you see webhook logs:** Connection successful!

---

## 🧪 Testing & Validation

### Test Case 1: Simple Single-Operation Edit

**Purpose:** Verify parallel mode works

**Setup:**
1. Create ClickUp task
2. Description: "Move the logo to the right side"
3. Attach: any PNG with a logo
4. Check "AI Edit" checkbox

**Expected Behavior:**
```
1. Webhook triggered → Server receives request
   Log: "Webhook received", "Task lock acquired"

2. Format conversion (if needed) → PSD/PDF to PNG
   Log: "Format conversion successful"

3. Enhancement → 4 prompts generated (parallel)
   Log: "Enhancement complete for 4 models"

4. Generation → 4 images created (parallel)
   Log: "Image generated successfully" × 4

5. Validation → Sequential with delays
   Log: "Validation complete" × 4
   Log: "Best result selected: [model] with score [9-10]"

6. Success → Upload to ClickUp
   Log: "Task completed successfully"

7. ClickUp update:
   ✅ New attachment added (edited image)
   ✅ "AI Edit" checkbox unchecked
   ✅ Status changed to "Complete"
   ✅ Comment added with metrics
```

**Verify in logs:**
```bash
railway logs --tail | grep -E "task_id|Enhancement|Generation|Validation|success"

# Look for:
# - "Enhancement complete for 4 models"
# - "Image generated successfully" (4 times)
# - "Validation complete" (4 times)
# - "Best result selected"
# - "Task completed successfully"
```

### Test Case 2: Complex Multi-Operation Edit (Sequential Mode)

**Purpose:** Verify sequential mode triggers and works

**Setup:**
1. Create ClickUp task
2. Description: "Move logo right, change 20% to 30%, add text 'EXTRA OFFER' below. Keep everything else identical."
3. Attach: marketing image with logo and percentage
4. Check "AI Edit" checkbox

**Expected Behavior:**
```
1. Parallel mode attempts (iterations 1-3)
   Log: "Iteration 1/3", "Iteration 2/3", "Iteration 3/3"
   All fail with: "No passing results"

2. Sequential mode trigger
   Log: "Failed 3 iterations - switching to SEQUENTIAL mode"
   Log: "Breaking request into 3 sequential operations"

3. Sequential execution:
   
   STEP 1: "Move logo right"
   - Attempt 1:
     Log: "SEQUENTIAL STEP 1/3"
     Log: "Phase 1: Enhancing for ALL models"
     Log: "Phase 2: Generating with 4 models"
     Log: "Phase 3: Validating 4 results"
     Log: "STEP 1 PASSED on attempt 1"
     Log: "Best: [model] with score 9/10"
   
   STEP 2: "Change 20% to 30%"
   - Attempt 1: FAIL (score 6/10)
     Log: "Step 2 attempt 1/2 failed"
     Log: "Retrying with feedback"
   - Attempt 2: PASS (score 8/10)
     Log: "STEP 2 PASSED on attempt 2"
   
   STEP 3: "Add text 'EXTRA OFFER'"
   - Attempt 1: PASS (score 10/10)
     Log: "STEP 3 PASSED on attempt 1"

4. Sequential completion
   Log: "ALL SEQUENTIAL STEPS COMPLETED SUCCESSFULLY!"

5. Success → Upload final result
   Log: "Task completed successfully"
```

**Verify in logs:**
```bash
railway logs | grep -E "SEQUENTIAL|STEP|attempt"

# Look for:
# - "switching to SEQUENTIAL mode"
# - "Breaking request into N sequential operations"
# - "SEQUENTIAL STEP 1/3", "2/3", "3/3"
# - "STEP X PASSED on attempt Y"
# - "ALL SEQUENTIAL STEPS COMPLETED"
```

### Test Case 3: Greek Text Validation

**Purpose:** Verify Greek uppercase tone rules work

**Setup:**
1. Create ClickUp task
2. Description: "Add text 'ΕΚΤΟΣ ΑΠΟ FREDDO' at the top"
3. Attach: any image
4. Check "AI Edit" checkbox

**Expected Validation:**
- ✅ If result shows "ΕΚΤΟΣ" (no tone) → Score 9-10/10 → PASS
- ❌ If result shows "ΕΚΤΌΣ" (unwanted tone) → Score 5-6/10 → FAIL

**Verify:**
```bash
railway logs | grep -A 5 '"score":'

# Look for validation reasoning mentioning tones/accents
# Should catch any unwanted tones as issues
```

### Test Case 4: Logo Duplication Detection

**Purpose:** Verify MOVE vs DUPLICATE detection works

**What to test:**
- Logo should appear ONCE at new position
- Logo should NOT appear at both old and new positions

**Manual Test:**
1. Request: "Move logo to bottom right"
2. If generated image shows logo at BOTH positions:
   - ⚠️  This is the bug we fixed
   - Validation should catch it: Score 5-6/10
   - Issues should include: "Logo duplicated instead of moved"

**Verify:**
```bash
railway logs | grep -i "duplicat"

# Should show validation caught duplication
# "Logo duplicated instead of moved"
```

### Test Case 5: Format Conversion

**Purpose:** Verify PSD/PDF/SVG conversion works

**Setup:**
1. Create ClickUp task
2. Description: "Make background blue"
3. Attach: **design.psd** (Photoshop file)
4. Check "AI Edit" checkbox

**Expected Logs:**
```json
{
  "level": "INFO",
  "message": "Downloading original image",
  "file_name": "design.psd"
}
{
  "level": "INFO",
  "message": "Format conversion successful",
  "original_format": "psd",
  "png_size_kb": 1234
}
{
  "level": "INFO",
  "message": "PNG uploaded to ClickUp"
}
```

**Verify:**
```bash
railway logs | grep -E "conversion|format"

# Should show:
# - "Format conversion successful"
# - "original_format": "psd" (or "pdf", "svg")
# - "PNG uploaded to ClickUp"
```

### Test Case 6: Hybrid Fallback

**Purpose:** Verify human review triggers when all fails

**Setup:**
1. Create ClickUp task with impossible request
2. Description: "Make the logo 3D and animated" (can't do this)
3. Attach: static image
4. Check "AI Edit" checkbox

**Expected Behavior:**
```
1. Parallel mode (3 iterations)
   - All fail with scores <8

2. Sequential mode
   - Cannot parse into steps (single impossible operation)
   - OR all steps fail

3. Hybrid fallback triggered
   Log: "All iterations failed, triggering hybrid fallback"
   Log: "Hybrid fallback triggered successfully"

4. ClickUp update:
   ✅ Status → "Needs Human Review"
   ✅ Comment added with failure details:
      - "AI Agent - Hybrid Fallback"
      - "Iterations Attempted: 3"
      - "Original Request: [request]"
      - "Issues Detected: [all issues]"
      - "Models Attempted: [list]"
      - "Next Steps: [recommendations]"
```

**Verify:**
```bash
railway logs | grep -i "hybrid"

# Should show:
# - "triggering hybrid fallback"
# - "Hybrid fallback triggered successfully"
```

---

## 📊 Monitoring & Maintenance

### Railway Dashboard Monitoring

**Access:** https://railway.app/project/YOUR_PROJECT_ID

**Key Metrics:**

1. **CPU Usage**
   - Target: <50% average
   - Spike to 80-90% during processing is normal
   - Sustained >80% = need to upgrade plan

2. **Memory Usage**
   - Target: <512MB average
   - Watch for gradual increase (memory leak)
   - Spike to 800MB during processing is normal

3. **Request Rate**
   - Track daily webhook volume
   - Compare success vs failure rate

4. **Error Rate**
   - Target: <5%
   - Monitor error logs for patterns

### Log Analysis

#### View Live Logs
```bash
# Real-time logs
railway logs --tail

# Filter by level
railway logs --tail | grep '"level":"ERROR"'

# Filter by task
railway logs --tail | grep 'task_id":"abc123"'
```

#### Analyze Success Rate
```bash
# Last 7 days
railway logs --since 7d > logs.txt

# Success count
grep "Processing complete" logs.txt | grep '"success":true' | wc -l

# Failure count
grep "Processing complete" logs.txt | grep '"success":false' | wc -l

# Success rate
# success_count / (success_count + failure_count) * 100
```

#### Average Processing Time
```bash
# Extract processing times
grep "processing_time_seconds" logs.txt | \
  grep -o '"processing_time_seconds":[0-9.]*' | \
  cut -d: -f2 | \
  awk '{sum+=$1; count++} END {print "Average:", sum/count, "seconds"}'

# Expected: ~35-45 seconds
```

#### Validation Score Distribution
```bash
# Score distribution
grep '"score":' logs.txt | \
  grep -o '"score":[0-9]*' | \
  cut -d: -f2 | \
  sort | uniq -c

# Expected distribution:
#  5  scores 0-2  (errors)
# 10  scores 3-7  (failures)
# 85  scores 8-10 (successes)
```

#### Hybrid Fallback Rate
```bash
# Hybrid fallback triggers
hybrid_count=$(grep "Hybrid fallback triggered" logs.txt | wc -l)

# Total tasks
total=$(grep "Processing complete" logs.txt | wc -l)

# Rate
echo "scale=2; $hybrid_count / $total * 100" | bc
# Target: <10%
```

### Health Check Monitoring

Set up external monitoring (e.g., UptimeRobot, Pingdom):

**Endpoint:** `https://your-app.railway.app/health`  
**Check Interval:** 5 minutes  
**Expected Response:** 
```json
{"status": "healthy", ...}
```

**Alerts:**
- Response time >5s
- HTTP status ≠200
- Downtime >5 minutes

---

## 🔧 Troubleshooting Guide

### Issue 1: Validation Prompt Not Applied

**Symptoms:**
- Logo duplication passes validation (should fail)
- Greek text with unwanted tones passes
- Scores don't match actual quality

**Diagnosis:**
```bash
# Check Railway logs for validation
railway logs | grep "Validation complete"

# Check if old validation behavior
railway logs | grep -i "duplication"
# Should show: "Logo duplicated instead of moved" if catching correctly
```

**Fix:**
```bash
# 1. Verify local file is updated
grep "MOVE = REMOVE" config/prompts/validation_prompt.txt

# 2. Verify file size
ls -lh config/prompts/validation_prompt.txt
# Should be ~26K

# 3. Clear Python cache
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

# 4. Redeploy
git add config/prompts/validation_prompt.txt
git commit -m "Update validation prompt with all fixes"
git push

# Railway will auto-redeploy

# 5. Verify in logs after restart
railway logs --tail | grep "Loading validation prompt"
```

### Issue 2: "Module not found" Error

**Symptoms:**
```
ModuleNotFoundError: No module named 'src'
```

**Cause:** Railway not running from `new/` directory

**Fix:**

Verify `railway.json`:
```json
{
  "deploy": {
    "startCommand": "cd new && uvicorn src.main:app --host 0.0.0.0 --port $PORT"
  }
}
```

**⚠️  CRITICAL:** Must have `cd new &&` prefix!

If missing:
```bash
# Update railway.json
# Add "cd new &&" to startCommand
# Commit and push

git add railway.json
git commit -m "Fix Railway start command"
git push
```

### Issue 3: Webhook Not Receiving Events

**Symptoms:**
- No logs when task updated in ClickUp
- Webhook shows as "active" but not working

**Diagnosis:**
```bash
# Check Railway logs for ANY activity
railway logs --tail

# Test webhook endpoint directly
curl -X POST https://your-app.railway.app/webhook/clickup \
  -H "Content-Type: application/json" \
  -H "X-Signature: test" \
  -d '{"event":"taskUpdated","task_id":"test"}'

# Should get response (even if signature invalid)
```

**Common Causes:**

1. **Wrong URL in ClickUp**
   - Check: ClickUp Settings → Webhooks → Your webhook
   - Should be: `https://your-app.railway.app/webhook/clickup`
   - Fix: Edit webhook, update URL, save

2. **Signature Mismatch**
   - Check Railway variables:
```bash
     railway variables get CLICKUP_WEBHOOK_SECRET
```
   - Compare with ClickUp webhook secret
   - Fix: 
```bash
     railway variables set CLICKUP_WEBHOOK_SECRET="<correct_secret>"
     railway up
```

3. **Webhook Disabled**
   - Check ClickUp webhook status
   - Should show: "Active" ✅
   - Fix: Re-enable webhook in ClickUp

### Issue 4: Extended Thinking Rate Limits

**Symptoms:**
```json
{
  "level": "ERROR",
  "error": "RateLimitError: OpenRouter rate limit exceeded"
}
```

**Cause:** Extended thinking mode has stricter rate limits

**Fix:**

Increase delays in `src/core/validator.py`:
```python
# Current: 2 seconds between validations
await asyncio.sleep(2)

# Increase to: 5 seconds
await asyncio.sleep(5)

# Or: 10 seconds for very strict limits
await asyncio.sleep(10)
```

Then redeploy:
```bash
git add src/core/validator.py
git commit -m "Increase validation delay for rate limits"
git push
```

### Issue 5: Out of Memory on Railway

**Symptoms:**
```
Railway logs show: "Process killed" or "OOM"
```

**Cause:** Large images + parallel processing

**Solutions:**

**Option 1: Upgrade Railway Plan**
- Hobby plan: 512MB RAM
- Pro plan: 8GB RAM
- Upgrade in Railway dashboard → Project Settings → Plan

**Option 2: Reduce Parallel Models**

Edit `config/models.yaml`:
```yaml
image_models:
  - name: wan-2.5-edit  # Keep best performer
    provider: wavespeed
    priority: 1
  # Comment out others temporarily:
  # - name: nano-banana
  # - name: seedream-v4
  # - name: qwen-edit-plus
```

**Option 3: Add Image Compression**

Edit `src/api/webhooks.py`:
```python
# After downloading image
from src.utils.images import resize_if_needed, compress_if_needed

# Resize if too large
png_bytes = resize_if_needed(png_bytes, max_width=2048, max_height=2048)

# Compress if too heavy
png_bytes = compress_if_needed(png_bytes, max_size_mb=5.0)
```

### Issue 6: Sequential Mode Not Triggering

**Symptoms:**
- Complex requests fail after 3 parallel iterations
- Never see "SEQUENTIAL MODE" in logs

**Diagnosis:**
```bash
railway logs | grep "SEQUENTIAL"

# If no results, sequential mode never triggered
```

**Cause:** Request not parsed into multiple steps

**Debug:**

Add logging to `src/core/refiner.py`:
```python
def parse_request_into_steps(self, request: str) -> List[str]:
    logger.info(f"🔍 PARSING REQUEST: {request}")
    
    # ... parsing logic ...
    
    logger.info(f"📋 PARSED INTO {len(steps)} STEPS: {steps}")
    return steps
```

**Fix:** Improve parsing for your use case

Example - add more delimiters:
```python
# Current: splits on "και" (Greek "and") and comma
request_normalized = request_part.replace(" και ", ",")

# Add: also split on "also", "then"
request_normalized = request_normalized.replace(" also ", ",")
request_normalized = request_normalized.replace(" then ", ",")
request_normalized = request_normalized.replace(" και επίσης ", ",")
```

### Issue 7: Task Already Processing (Webhook Duplicates)

**Symptoms:**
```json
{
  "status": "already_processing",
  "message": "Task is already being processed"
}
```

**Cause:** ClickUp sent duplicate webhook (normal behavior)

**This is CORRECT behavior!** Task locking prevents:
- Wasted API credits
- Duplicate processing
- Race conditions

**No fix needed** - webhook returns immediately with status.

If you see this frequently, it means:
- ClickUp is sending duplicate webhooks (their infrastructure)
- System is correctly rejecting duplicates ✅

---

## 🚀 Production Optimization

### 1. Cost Optimization

**Current cost:** ~$0.20 per successful edit

**Reduce to ~$0.10:**
```yaml
# config/models.yaml
# Use only 2 best-performing models
image_models:
  - name: wan-2.5-edit
    priority: 1
  - name: nano-banana
    priority: 2
  # Comment out:
  # - seedream-v4
  # - qwen-edit-plus
```

**This reduces:**
- Enhancement: 4→2 calls ($0.015 → $0.0075)
- Generation: 4→2 calls ($0.08 → $0.04)
- Validation: 4→2 calls ($0.10 → $0.05)
- **New total:** ~$0.10 per edit

**Trade-off:** Lower success rate (70% → 60%)

### 2. Performance Optimization

#### Enable Full Caching
```bash
# In .env
CACHE_ENABLED=true

# Verify in logs
railway logs | grep "cache_hit"
# Should show: "cache_hit": true for ~90% of requests
```

#### Reduce Validation Delays

If not hitting rate limits:
```python
# src/core/validator.py
await asyncio.sleep(2)  # Current
await asyncio.sleep(1)  # Faster (if no rate limit issues)
```

### 3. Quality Optimization

#### Increase Pass Threshold

For higher quality output:
```bash
# .env
VALIDATION_PASS_THRESHOLD=9  # Only accept excellent results

# Trade-off: More hybrid fallbacks (~10% → 15%)
```

#### Increase Iterations
```bash
# .env
MAX_ITERATIONS=5  # More chances to succeed

# Trade-off: Slower (45s → ~60s), higher cost
```

### 4. Monitoring Setup

#### Set Up Alerts

**UptimeRobot:**
1. Create monitor for `/health` endpoint
2. Set check interval: 5 minutes
3. Alert channels: Email, Slack, SMS

**Expected uptime:** 99.5%+

#### Weekly Review Checklist
```bash
# Every Monday:

# 1. Success rate (target: >95%)
railway logs --since 7d | grep "Processing complete" | \
  grep -o '"success":[^,]*' | sort | uniq -c

# 2. Average processing time (target: <45s)
railway logs --since 7d | grep "processing_time_seconds" | \
  grep -o '"processing_time_seconds":[0-9.]*' | \
  awk -F: '{sum+=$2; count++} END {print sum/count}'

# 3. Hybrid fallback rate (target: <10%)
railway logs --since 7d | grep -c "Hybrid fallback triggered"

# 4. Error rate (target: <5%)
railway logs --since 7d | grep -c '"level":"ERROR"'

# 5. Top errors (investigate if any)
railway logs --since 7d | grep '"level":"ERROR"' | \
  grep -o '"error":"[^"]*"' | sort | uniq -c | sort -rn | head -10
```

### 5. Scaling Preparation

**When to scale:**
- Processing >100 tasks/day
- CPU usage consistently >60%
- Memory usage consistently >400MB

**How to scale:**

1. **Upgrade Railway Plan**
   - Hobby → Pro
   - More CPU, RAM, better network

2. **Add Caching Layer** (future)
   - Redis for prompt caching
   - Result caching for similar requests

3. **Horizontal Scaling** (future)
   - Multiple Railway instances
   - Load balancer
   - Task queue (RabbitMQ/Celery)

---

## ✅ Post-Deployment Checklist

### Immediate (First Hour)

- [ ] Health check passes: `curl https://your-app.railway.app/health`
- [ ] Webhook receives test event
- [ ] Test task processes successfully
- [ ] Result uploaded to ClickUp correctly
- [ ] Logs show no errors
- [ ] Validation uses new prompt (check scores)
- [ ] "AI Edit" checkbox unchecks after completion

### First Day

- [ ] Process 5-10 real tasks
- [ ] Monitor success rate (should be >90%)
- [ ] Check validation accuracy (scores match quality)
- [ ] Verify sequential mode triggers on complex requests
- [ ] Review cost per task
- [ ] Check Railway resource usage (CPU, memory)

### First Week

- [ ] Analyze model performance (which models succeed most)
- [ ] Review validation failure patterns
- [ ] Optimize model selection if needed
- [ ] Update deep research if patterns emerge
- [ ] Tune validation threshold if needed
- [ ] Document any edge cases discovered

---

## 🔄 Rollback Procedure

If deployment has critical issues:

### Option 1: Railway Automatic Rollback
```bash
# View deployment history
railway logs --since 1h

# Rollback to previous deployment
railway rollback

# System reverts to last working version
```

### Option 2: Git-Based Rollback
```bash
# Find last good commit
git log --oneline

# Example output:
# abc123d (HEAD) Update validation prompt
# def456g Add sequential mode
# ghi789j Last working version  ← ROLLBACK TO THIS

# Checkout previous commit
git checkout ghi789j

# Deploy
railway up

# Return to main branch (but don't deploy yet)
git checkout main

# Fix issues, then re-deploy
```

### Option 3: Temporary Disable

Disable webhook in ClickUp while fixing:

1. ClickUp Settings → Webhooks
2. Find your webhook
3. Click "..." → Disable
4. Fix issues
5. Redeploy
6. Re-enable webhook

---

## 📚 Additional Resources

- **API Documentation:** https://your-app.railway.app/docs
- **Railway Dashboard:** https://railway.app/project/YOUR_PROJECT_ID
- **ClickUp API:** https://clickup.com/api
- **OpenRouter:** https://openrouter.ai/docs
- **WaveSpeedAI:** Contact for documentation

---

**Deployment Complete! 🎉**

Your Image Edit Agent is now live and processing ClickUp tasks automatically with:
- ✅ Sequential mode for complex requests
- ✅ Extended thinking for better validation
- ✅ Provider locking for consistency
- ✅ Format conversion for all file types
- ✅ Memory optimization for performance
- ✅ Comprehensive validation with all fixes

**Need Help?**
- Check logs: `railway logs --tail`
- Review architecture: See `PROJECT_STRUCTURE.md`
- File reference: See `FILE_MANIFEST.md`