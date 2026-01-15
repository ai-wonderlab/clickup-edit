# 🎚️ FEATURE FLAG: Dual Orchestrator System

## 📋 Overview

The system now supports **TWO orchestrators** with a feature flag to switch between them:

1. **OLD Orchestrator** (Single Validation) - Default
2. **NEW Orchestrator** (Dual Validation + Smart Retry) - Optional

---

## 🔧 How to Switch

### Environment Variable

Set the `USE_NEW_ORCHESTRATOR` environment variable:

```bash
# Use NEW orchestrator (Dual Validation + Smart Retry)
USE_NEW_ORCHESTRATOR=true

# Use OLD orchestrator (Single Validation) - DEFAULT
USE_NEW_ORCHESTRATOR=false
# or don't set it at all
```

### In `.env` file:

```bash
# Enable new orchestrator
USE_NEW_ORCHESTRATOR=true
```

### Railway/Production:

Add environment variable in Railway dashboard:
- **Key:** `USE_NEW_ORCHESTRATOR`
- **Value:** `true` or `false`

---

## 🏗️ Architecture

### Initialization (main.py)

```python
# BOTH orchestrators are initialized at startup
orchestrator = Orchestrator(...)           # OLD
orchestrator_new = OrchestratorWithSmartRetry(...)  # NEW

# Feature flag decides which is active
USE_NEW_ORCHESTRATOR = os.getenv('USE_NEW_ORCHESTRATOR', 'false').lower() == 'true'

if USE_NEW_ORCHESTRATOR:
    active_orchestrator = orchestrator_new  # 🚀 NEW
else:
    active_orchestrator = orchestrator      # 📌 OLD (default)

# All three stored in app.state
app.state.orchestrator = orchestrator           # OLD
app.state.orchestrator_new = orchestrator_new   # NEW
app.state.active_orchestrator = active_orchestrator  # 🎯 ACTIVE
```

### Webhook Handler (webhooks.py)

```python
async def get_orchestrator(request: Request):
    """Returns the ACTIVE orchestrator based on feature flag."""
    return request.app.state.active_orchestrator

# Automatic method detection
if hasattr(orchestrator, 'process_with_smart_retry'):
    # New orchestrator
    result = await orchestrator.process_with_smart_retry(...)
else:
    # Old orchestrator
    result = await orchestrator.process_with_iterations(...)
```

---

## 📊 Comparison

| Feature | OLD Orchestrator | NEW Orchestrator |
|---------|-----------------|------------------|
| **Validation Models** | 1 (Claude Sonnet) | 2 (Sonnet + Haiku) |
| **Pass Criteria** | Single score ≥8.0 | Both scores ≥9.0 (consensus) |
| **Retry Logic** | Fixed iterations | Smart retry (5 attempts) |
| **Retry Strategy** | Same prompt | Incremental/Catastrophic |
| **Image Reuse** | ❌ No | ✅ Yes (if score ≥8.0) |
| **Strictness** | Medium | High |
| **Cost** | Lower | Higher (2 validations) |
| **Quality** | Good | Excellent |

---

## 🎯 When to Use Each

### Use OLD Orchestrator When:
- ✅ Cost is a concern
- ✅ Speed is priority
- ✅ Good quality is acceptable
- ✅ Testing/development
- ✅ Lower volume workloads

### Use NEW Orchestrator When:
- ✅ **Highest quality required** ⭐
- ✅ Client-facing production
- ✅ Budget allows for dual validation
- ✅ Consensus validation needed
- ✅ Smart retry logic beneficial

---

## 🔄 Switching Between Orchestrators

### Development:
```bash
# Test OLD
unset USE_NEW_ORCHESTRATOR
# or
export USE_NEW_ORCHESTRATOR=false

# Test NEW
export USE_NEW_ORCHESTRATOR=true
```

### Production (Railway):

1. Go to Railway dashboard
2. Select your service
3. Go to **Variables** tab
4. Add/modify `USE_NEW_ORCHESTRATOR`
5. Redeploy (automatic)

---

## 🚨 Important Notes

### Both Orchestrators Share:
- ✅ Same enhancement system
- ✅ Same generation system
- ✅ Same hybrid fallback
- ✅ Same ClickUp integration
- ✅ Same PNG memory optimization

### Only Difference:
- ❌ Validation strategy (single vs dual)
- ❌ Retry logic (fixed vs smart)
- ❌ Strictness level (medium vs high)

---

## 📈 Logs

### OLD Orchestrator:
```
📌 Using OLD orchestrator (Single Validation)
```

### NEW Orchestrator:
```
🚀 Using NEW orchestrator (Dual Validation + Smart Retry)
```

---

## 🧪 Testing Both

### Test OLD:
```bash
export USE_NEW_ORCHESTRATOR=false
python -m uvicorn src.main:app --reload
```

### Test NEW:
```bash
export USE_NEW_ORCHESTRATOR=true
python -m uvicorn src.main:app --reload
```

### Check Active Orchestrator:
Look for startup logs:
```
📌 Using OLD orchestrator (Single Validation)
# or
🚀 Using NEW orchestrator (Dual Validation + Smart Retry)
```

---

## 💡 Recommendation

**Start with OLD orchestrator** (default) and switch to NEW once:
1. ✅ System is stable
2. ✅ Budget confirmed for dual validation
3. ✅ Quality requirements increase
4. ✅ Ready for production workload

**Enable NEW orchestrator** with:
```bash
USE_NEW_ORCHESTRATOR=true
```

---

## 🎉 Benefits

1. **Zero Downtime Switching** - Both orchestrators ready
2. **Instant Rollback** - Just flip the flag
3. **A/B Testing** - Compare quality/cost
4. **Gradual Migration** - Test NEW before full switch
5. **Fallback Safety** - OLD always available

---

## 🔧 Future Enhancements

Potential additions:
- Per-task orchestrator selection
- Auto-switching based on load
- Quality metrics comparison
- Cost tracking per orchestrator
