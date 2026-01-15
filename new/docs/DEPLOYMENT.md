# Deployment Guide - Image Edit Agent

## Table of Contents
1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Subfolder Context](#subfolder-context)
3. [Local Development Setup](#local-development-setup)
4. [Validation Prompt Verification](#validation-prompt-verification)
5. [Railway Deployment](#railway-deployment)
6. [ClickUp Configuration](#clickup-configuration)
7. [Testing & Verification](#testing--verification)
8. [Monitoring](#monitoring)
9. [Troubleshooting](#troubleshooting)

---

## Pre-Deployment Checklist

### ✅ Critical Files Verification

Run these checks from the `new/` directory:

```bash
# 1. Verify validation prompt is updated
grep -q "MOVE = REMOVE from old position" config/prompts/validation_prompt.txt && echo "✅ Validation prompt updated" || echo "❌ OLD PROMPT!"

# 2. Check validation prompt for Greek tone rules
grep -q "Uppercase Greek should have NO tones" config/prompts/validation_prompt.txt && echo "✅ Greek tone rules present" || echo "❌ Missing!"

# 3. Check validation prompt for logo preservation
grep -q "Logo DESIGN pixel-identical" config/prompts/validation_prompt.txt && echo "✅ Logo preservation rules present" || echo "❌ Missing!"

# 4. Verify all deep research files exist
for model in wan-2.5-edit nano-banana seedream-v4 qwen-edit-plus; do
  [ -f "config/deep_research/$model/activation.txt" ] && [ -f "config/deep_research/$model/research.md" ] && echo "✅ $model research complete" || echo "❌ $model research missing"
done

# 5. Check Python files for png_bytes usage
grep -q "original_image_bytes" src/api/webhooks.py && echo "✅ webhooks.py updated" || echo "❌ OLD CODE!"
grep -q "original_image_bytes" src/core/orchestrator.py && echo "✅ orchestrator.py updated" || echo "❌ OLD CODE!"
grep -q "original_image_bytes" src/providers/openrouter.py && echo "✅ openrouter.py updated" || echo "❌ OLD CODE!"
```

**All checks must pass ✅ before deploying!**

---

### 📋 API Keys Checklist

Collect these API keys before proceeding:

- [ ] **OpenRouter API Key** - Get from https://openrouter.ai/keys
- [ ] **WaveSpeedAI API Key** - Get from WaveSpeedAI dashboard
- [ ] **ClickUp API Key** - Get from ClickUp Settings → Apps
- [ ] **ClickUp Webhook Secret** - Will get after creating webhook
- [ ] **ClickUp AI Edit Field ID** - `b2c19afd-0ef2-485c-94b9-3a6124374ff4` (provided)

---

### 📁 Deep Research Files Checklist

Ensure all 8 files exist with content:

```bash
config/deep_research/
├── wan-2.5-edit/
│   ├── activation.txt     [ ] ~500 tokens
│   └── research.md        [ ] ~5-8K tokens
├── nano-banana/
│   ├── activation.txt     [ ] ~500 tokens
│   └── research.md        [ ] ~5-8K tokens
├── seedream-v4/
│   ├── activation.txt     [ ] ~500 tokens
│   └── research.md        [ ] ~5-8K tokens
└── qwen-edit-plus/
    ├── activation.txt     [ ] ~500 tokens
    └── research.md        [ ] ~5-8K tokens
```

---

## Subfolder Context

### Understanding Your Setup

**Your project structure:**
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

**Key implications:**
1. Git commands run from **main-repo root**
2. Railway must deploy from **new/ subdirectory**
3. `railway.json` handles subfolder context
4. All relative paths work from `new/` directory

---

### Railway Configuration for Subfolder

Your `railway.json` (already configured):

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
- ✅ Install dependencies from `new/requirements.txt`
- ✅ Change directory to `new/` before starting
- ✅ Run uvicorn from `new/` directory
- ✅ All relative imports work correctly

---

## Local Development Setup

### Step 1: Navigate to Project Directory

```bash
# From main-repo root:
cd new/

# Verify you're in the right place:
ls -la
# Should see: config/, src/, requirements.txt, railway.json, etc.
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
```

**Expected packages:**
- fastapi==0.109.0
- pydantic==2.5.0
- httpx==0.26.0
- Pillow==10.2.0
- psd-tools==1.9.31
- cairosvg==2.7.1
- (and others)

### Step 4: Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your API keys
nano .env  # or use your preferred editor
```

**Fill in ALL required values:**

```env
# OpenRouter (Claude + Gemini)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxx

# WaveSpeedAI (Image generation)
WAVESPEED_API_KEY=ws_xxxxxxxxxxxxxxxxxxxxx

# ClickUp (Task management)
CLICKUP_API_KEY=pk_xxxxxxxxxxxxxxxxxxxxx
CLICKUP_WEBHOOK_SECRET=<will_get_after_creating_webhook>
CLICKUP_AI_EDIT_FIELD_ID=b2c19afd-0ef2-485c-94b9-3a6124374ff4

# Configuration
IMAGE_MODELS=wan-2.5-edit,nano-banana,seedream-v4,qwen-edit-plus
MAX_ITERATIONS=3
VALIDATION_PASS_THRESHOLD=8
APP_ENV=development
LOG_LEVEL=INFO
```

### Step 5: Verify Configuration Loading

```bash
# Test configuration
python -c "
from src.utils.config import load_config, load_validation_prompt
config = load_config()
prompt = load_validation_prompt()
print(f'✅ Config loaded: {len(config.image_models)} models')
print(f'✅ Validation prompt loaded: {len(prompt)} characters')
print(f'✅ MOVE fix present: {\"MOVE = REMOVE\" in prompt}')
print(f'✅ Greek tone fix present: {\"NO tones\" in prompt}')
print(f'✅ Logo fix present: {\"pixel-identical\" in prompt}')
"
```

**Expected output:**
```
✅ Config loaded: 4 models
✅ Validation prompt loaded: 26000 characters
✅ MOVE fix present: True
✅ Greek tone fix present: True
✅ Logo fix present: True
```

**If any False:** Your validation prompt is not updated! Re-upload the fixed version.

### Step 6: Start Local Server

```bash
# Start uvicorn
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

**Expected output:**
```
INFO:     Will watch for changes in these directories: ['.../new']
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using WatchFiles
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### Step 7: Test Health Check

```bash
# In a new terminal (keep server running):
curl http://localhost:8000/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-23T...",
  "service": "image-edit-agent",
  "version": "1.0.0"
}
```

### Step 8: View API Documentation

Open browser: http://localhost:8000/docs

**You should see:**
- Swagger UI with all endpoints
- `/webhook/clickup` endpoint
- `/health` endpoint
- Try out feature for testing

---

## Validation Prompt Verification

### Critical Verification Steps

**Before deploying, MUST verify the validation prompt has all fixes!**

```bash
# 1. Check file size (should be ~26KB)
ls -lh config/prompts/validation_prompt.txt
# Expected: ~26K

# 2. Verify line count (should be ~645 lines)
wc -l config/prompts/validation_prompt.txt
# Expected: ~645

# 3. Check for critical fixes
echo "=== CHECKING CRITICAL FIXES ==="

# Fix 1: MOVE vs DUPLICATE
grep -A 4 "CRITICAL MOVE RULES" config/prompts/validation_prompt.txt
# Should show: "MOVE = REMOVE from old position + ADD to new position"

# Fix 2: Logo design preservation
grep -A 5 "LOGO PRESERVATION" config/prompts/validation_prompt.txt
# Should show: "Logo DESIGN pixel-identical"

# Fix 3: Greek uppercase tones
grep -A 5 "UPPERCASE GREEK - TONE" config/prompts/validation_prompt.txt
# Should show: "Uppercase Greek should have NO tones/accents"

# Fix 4: Tolerance rules
grep -A 5 "TOLERANCE AND ACCEPTABLE" config/prompts/validation_prompt.txt
# Should show clear thresholds

# Fix 5: Example count
grep -c "^Example" config/prompts/validation_prompt.txt
# Should show: 20

echo "=== VERIFICATION COMPLETE ==="
```

**All checks must pass!** If any fail, re-upload the validation prompt.

### Test Validation Logic Locally

```bash
# Create a test script
cat > test_validation.py << 'EOF'
import asyncio
from src.utils.config import load_validation_prompt

async def test():
    prompt = load_validation_prompt()
    
    print(f"Prompt length: {len(prompt)} chars")
    print(f"Prompt lines: {len(prompt.split(chr(10)))}")
    
    # Check for critical sections
    checks = {
        "MOVE rules": "MOVE = REMOVE from old position" in prompt,
        "Logo preservation": "Logo DESIGN pixel-identical" in prompt,
        "Greek tones": "NO tones/accents UNLESS" in prompt,
        "Aspect ratio": "Maintain aspect ratio" in prompt,
        "Effects move": "move WITH element" in prompt,
        "Background restoration": "Background must be restored" in prompt,
        "Color precision": "RGB units per channel" in prompt,
    }
    
    print("\n=== VALIDATION CHECKS ===")
    for name, result in checks.items():
        status = "✅" if result else "❌"
        print(f"{status} {name}: {result}")
    
    all_pass = all(checks.values())
    print(f"\n{'✅ ALL CHECKS PASSED!' if all_pass else '❌ SOME CHECKS FAILED!'}")

asyncio.run(test())
EOF

# Run test
python test_validation.py

# Clean up
rm test_validation.py
```

---

## Railway Deployment

### Prerequisites

**1. Install Railway CLI:**
```bash
# macOS
brew install railway

# Or via npm
npm install -g @railway/cli

# Verify installation
railway --version
```

**2. Login to Railway:**
```bash
railway login
# Opens browser for authentication
```

### Deployment Steps

#### Step 1: Link to Existing Railway Project

```bash
# From main-repo root (NOT new/ subdirectory)
cd /path/to/main-repo

# Link to your existing Railway project
railway link
# Select your project from the list
```

#### Step 2: Verify Railway Configuration

```bash
# Check railway.json exists
cat new/railway.json

# Should show subfolder-aware config:
# - buildCommand: "pip install -r new/requirements.txt"
# - startCommand: "cd new && uvicorn src.main:app ..."
```

#### Step 3: Set Environment Variables

```bash
# Set all required environment variables
railway variables set OPENROUTER_API_KEY="sk-or-v1-xxxxxxxxxxxxxxxxxxxxx"
railway variables set WAVESPEED_API_KEY="ws_xxxxxxxxxxxxxxxxxxxxx"
railway variables set CLICKUP_API_KEY="pk_xxxxxxxxxxxxxxxxxxxxx"
railway variables set CLICKUP_WEBHOOK_SECRET="<leave_empty_for_now>"
railway variables set CLICKUP_AI_EDIT_FIELD_ID="b2c19afd-0ef2-485c-94b9-3a6124374ff4"

# Configuration variables
railway variables set IMAGE_MODELS="wan-2.5-edit,nano-banana,seedream-v4,qwen-edit-plus"
railway variables set MAX_ITERATIONS="3"
railway variables set VALIDATION_PASS_THRESHOLD="8"
railway variables set APP_ENV="production"
railway variables set LOG_LEVEL="INFO"

# Verify variables are set
railway variables
```

#### Step 4: Deploy

```bash
# From main-repo root:
railway up

# Railway will:
# 1. Detect railway.json
# 2. Install dependencies from new/requirements.txt
# 3. Start server from new/ directory
# 4. Provide a public URL
```

**Expected deployment logs:**
```
Building...
Running buildCommand: pip install -r new/requirements.txt
Successfully installed fastapi-0.109.0 pydantic-2.5.0 ...
Deploying...
Running startCommand: cd new && uvicorn src.main:app --host 0.0.0.0 --port 8000
INFO:     Started server process [1]
INFO:     Application startup complete.
Deployment successful!
```

#### Step 5: Get Your Railway URL

```bash
# Get the public URL
railway domain
```

**Copy the URL:** `https://your-app-name.up.railway.app`

---

### Verify Deployment

```bash
# Test health check
curl https://your-app-name.up.railway.app/health

# Should return:
# {"status":"healthy","timestamp":"...","service":"image-edit-agent","version":"1.0.0"}
```

---

## ClickUp Configuration

### Step 1: Create ClickUp Webhook

1. **Navigate to ClickUp Settings:**
   - Click avatar (bottom left)
   - Click **Settings**
   - Go to **Integrations** → **Webhooks**

2. **Create Webhook:**
   - Click **Create Webhook**
   - **Endpoint URL:** `https://your-app-name.up.railway.app/webhook/clickup`
   - **Events to watch:** Check `taskUpdated`
   - **Description:** "Image Edit Agent - Auto-processes image edits"

3. **Apply Filters (Optional but Recommended):**
   - **List:** Select specific list(s) where tasks need image editing
   - **Custom Field:** If you have "Needs AI Edit" checkbox, filter by that
   - **Tags:** Or filter by specific tags like "ai-edit"

4. **Save Webhook**

### Step 2: Copy Webhook Secret

After creating webhook, ClickUp shows the **Webhook Secret**.

**Copy this secret!** You'll need it for the next step.

### Step 3: Update Railway with Webhook Secret

```bash
# Set the webhook secret
railway variables set CLICKUP_WEBHOOK_SECRET="<paste_webhook_secret_here>"

# Redeploy (to pick up new env var)
railway up
```

### Step 4: Test Webhook

1. **Create a test task in ClickUp:**
   - Add a task description: "Move logo to the right"
   - Attach a PNG/PSD image
   - Update the task (to trigger webhook)

2. **Check Railway logs:**
```bash
railway logs --tail
```

**Expected log output:**
```json
{"timestamp":"...","level":"INFO","logger":"src.api.webhooks","message":"Webhook received","task_id":"abc123"}
{"timestamp":"...","level":"INFO","logger":"src.api.webhooks","message":"Task lock acquired","task_id":"abc123"}
{"timestamp":"...","level":"INFO","logger":"src.api.webhooks","message":"Fetching task from ClickUp","task_id":"abc123"}
{"timestamp":"...","level":"INFO","logger":"src.core.orchestrator","message":"Starting orchestration","task_id":"abc123"}
...
{"timestamp":"...","level":"INFO","logger":"src.core.orchestrator","message":"Orchestration complete","task_id":"abc123","success":true,"iterations":2}
```

3. **Check ClickUp task:**
   - New image attachment should be added
   - Task status should be updated
   - Comment should be added with results

---

## Testing & Verification

### Test Case 1: Simple Move Operation

**Create ClickUp task:**
- **Description:** "Move the logo to the right side"
- **Attachment:** Any image with a logo

**Expected behavior:**
1. Webhook triggers → Server receives request
2. Enhancement → 4 prompts generated
3. Generation → 4 images created
4. Validation → **NEW PROMPT** checks:
   - ✅ Logo moved to right
   - ✅ Logo appears ONCE (not duplicated)
   - ✅ Logo design unchanged
5. Best result uploaded to ClickUp
6. Task marked complete

**Verify in logs:**
```bash
railway logs --tail | grep -E "task_id|orchestration|validation"
```

### Test Case 2: Greek Text (Tone Check)

**Create ClickUp task:**
- **Description:** "Add text 'ΕΚΤΟΣ ΑΠΟ FREDDO' at the top"
- **Attachment:** Any image

**Expected validation behavior:**
- If result shows "ΕΚΤΟΣ" (no tone) → ✅ PASS
- If result shows "ΕΚΤΌΣ" (unwanted tone) → ❌ FAIL (score 6/10)

**Verify:** Check validation scores in logs

### Test Case 3: Logo Duplication (Should Fail)

**Manually test validation:**

If a model generates an image with logo in BOTH old and new positions:
- Validation should score 5-6/10
- Issues should include: "Logo duplicated instead of moved"
- Should try next iteration

**This was your original bug - now fixed!**

### Test Case 4: Hybrid Fallback

**Create ClickUp task with impossible edit:**
- **Description:** "Make the logo 3D and animated" (can't do this)

**Expected behavior:**
- Iteration 1 fails (score <8)
- Iteration 2 fails (score <8)
- Iteration 3 fails (score <8)
- **Hybrid fallback triggers:**
  - Task status → "HUMAN REVIEW NEEDED"
  - Comment added with all failure reasons
  - Human can take over

---

## Monitoring

### Railway Dashboard

**Key metrics to watch:**
- **CPU Usage:** Should be <50% average
- **Memory Usage:** Should be <512MB
- **Request Count:** Track daily volume
- **Error Rate:** Should be <5%

**Access:** https://railway.app/project/YOUR_PROJECT_ID

### Log Analysis

**View live logs:**
```bash
railway logs --tail
```

**Search for errors:**
```bash
railway logs | grep '"level":"ERROR"'
```

**Search specific task:**
```bash
railway logs | grep 'task_id":"abc123"'
```

### Success Metrics

**Monitor weekly:**
```bash
# Success rate (should be >95%)
railway logs --since 7d | grep "Orchestration complete" | grep -o '"success":[^,]*' | sort | uniq -c

# Average processing time (should be <45s)
railway logs --since 7d | grep "processing_time_seconds" | grep -o '"processing_time_seconds":[0-9.]*' | awk -F: '{sum+=$2; count++} END {print sum/count}'

# Hybrid fallback rate (should be <10%)
railway logs --since 7d | grep -c "Hybrid fallback triggered"
```

### Validation Accuracy

**Check validation scores:**
```bash
# Distribution of scores
railway logs --since 7d | grep '"score":' | grep -o '"score":[0-9]*' | sort | uniq -c

# Failed validations (score <8)
railway logs --since 7d | grep '"pass_fail":"FAIL"' | wc -l
```

---

## Troubleshooting

### Issue 1: Validation Prompt Not Updated

**Symptoms:**
- Logo duplication passes validation (score 10/10)
- Unwanted Greek tones pass validation
- Old validation behavior

**Diagnosis:**
```bash
# SSH into Railway (if available) or check logs
railway logs | grep "Loading validation prompt"

# Or test locally:
python -c "from src.utils.config import load_validation_prompt; print('MOVE = REMOVE' in load_validation_prompt())"
```

**Fix:**
```bash
# 1. Verify file exists and is updated
cat config/prompts/validation_prompt.txt | head -50
# Should show: "MOVE = REMOVE from old position"

# 2. Clear any Python cache
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

# 3. Redeploy
railway up

# 4. Verify in logs after restart
railway logs --tail | grep "validation prompt"
```

### Issue 2: "Module not found" Error

**Symptoms:**
```
ModuleNotFoundError: No module named 'src'
```

**Cause:** Railway not running from correct directory

**Fix:**

Check `railway.json`:
```json
{
  "deploy": {
    "startCommand": "cd new && uvicorn src.main:app --host 0.0.0.0 --port $PORT"
  }
}
```

**MUST have `cd new &&` before uvicorn!**

### Issue 3: Webhook Not Receiving Events

**Diagnosis:**
```bash
# Check Railway logs for incoming requests
railway logs --tail | grep webhook

# Test webhook endpoint directly
curl -X POST https://your-app-name.up.railway.app/webhook/clickup \
  -H "Content-Type: application/json" \
  -H "X-Signature: test" \
  -d '{"event":"taskUpdated","task_id":"test"}'
```

**Common causes:**
1. **Wrong URL:** Check ClickUp webhook configuration
2. **Signature mismatch:** Check `CLICKUP_WEBHOOK_SECRET`
3. **Webhook disabled:** Check ClickUp webhook is active

**Fix:**
```bash
# Verify webhook secret matches
railway variables get CLICKUP_WEBHOOK_SECRET
# Compare with ClickUp webhook secret

# Update if needed
railway variables set CLICKUP_WEBHOOK_SECRET="<correct_secret>"
railway up
```

### Issue 4: "Provider returned error" (OpenRouter)

**Symptoms:**
```
ProviderError: OpenRouter API returned 400
```

**Cause:** Usually image size or format issue

**Diagnosis:**
```bash
# Check logs for full error
railway logs | grep -A 10 "Provider returned error"
```

**Fix:**
1. **Image too large:** Add compression in `src/utils/images.py`
2. **Invalid base64:** Check `openrouter.py` encoding
3. **Rate limit:** Add exponential backoff (already implemented)

### Issue 5: Out of Memory

**Symptoms:**
```
Railway logs show: "Process killed" or "OOM"
```

**Cause:** Large images + parallel processing

**Fix:**
```bash
# 1. Upgrade Railway plan (more memory)
# 2. Add image compression before processing
# 3. Reduce parallel operations (edit config/models.yaml)
```

### Issue 6: Slow Performance

**Symptoms:**
- Tasks taking >60s to complete
- Timeouts

**Diagnosis:**
```bash
# Check processing times
railway logs | grep "processing_time_seconds"
```

**Common causes:**
1. **Cold start:** First request after deploy is slower (normal)
2. **Large images:** Compress before processing
3. **Network latency:** Check API response times
4. **Model slowness:** Check WaveSpeed status

**Fix:**
- Use Railway Pro (better performance)
- Implement image compression
- Add timeout handling (already implemented)

---

## Post-Deployment Checklist

### Immediate (First Hour)

- [ ] Health check passes: `curl https://your-app.railway.app/health`
- [ ] Webhook receives test event
- [ ] Test task processes successfully
- [ ] Result uploaded to ClickUp correctly
- [ ] Logs show no errors
- [ ] Validation uses NEW prompt (check scores)

### First Day

- [ ] Process 5-10 real tasks
- [ ] Monitor success rate (should be >90%)
- [ ] Check validation accuracy
- [ ] Verify hybrid fallback triggers appropriately
- [ ] Review cost per task
- [ ] Check Railway resource usage

### First Week

- [ ] Analyze model performance
- [ ] Review validation failure patterns
- [ ] Optimize model selection if needed
- [ ] Update deep research if needed
- [ ] Tune validation threshold if needed
- [ ] Document any edge cases

---

## Rollback Procedure

If deployment has critical issues:

```bash
# Option 1: Railway automatic rollback
railway rollback

# Option 2: Redeploy previous commit
git log --oneline  # Find previous good commit
git checkout <commit_hash>
railway up
git checkout main  # Return to main branch

# Option 3: Disable webhook in ClickUp
# (Temporarily stop processing while fixing)
```

---

## Security Best Practices

1. **Never commit `.env` file:**
```bash
# Verify .gitignore includes:
cat .gitignore | grep ".env"
# Should show: .env (not .env.example)
```

2. **Rotate API keys regularly:**
- OpenRouter: Monthly
- WaveSpeedAI: Monthly
- ClickUp: Quarterly

3. **Monitor for suspicious activity:**
```bash
# Check for unusual requests
railway logs | grep -E "401|403|429"
```

4. **Keep dependencies updated:**
```bash
pip list --outdated
# Update regularly, test before deploying
```

---

## Cost Optimization

**Current cost: ~$0.20 per successful edit**

**To reduce costs:**

1. **Reduce model count:**
```yaml
# In config/models.yaml
image_models:
  - name: wan-2.5-edit  # Keep only top performer
    priority: 1
  # Comment out others
```

2. **Increase validation threshold:**
```env
# In Railway variables
VALIDATION_PASS_THRESHOLD=7  # Accept score 7+
```

3. **Optimize prompt caching:**
- Ensure deep research files are stable
- Cache hit rate should be >90%

**Monitor costs:**
```bash
# Track API usage in provider dashboards
# - OpenRouter: https://openrouter.ai/usage
# - WaveSpeedAI: Check their dashboard
```

---

## Next Steps After Deployment

### Week 1: Monitor & Tune
- Watch validation accuracy
- Adjust thresholds if needed
- Document edge cases
- Collect user feedback

### Week 2: Optimize
- Analyze model performance
- Update deep research
- Optimize cost/performance
- Improve validation prompt if needed

### Month 1: Scale
- Increase task volume gradually
- Monitor Railway resources
- Consider multi-region deployment
- Implement advanced features (queuing, caching)

---

**Deployment Complete! 🚀**

Your Image Edit Agent is now live and processing ClickUp tasks automatically with all critical fixes in place.

**Need help?** Check logs: `railway logs --tail`