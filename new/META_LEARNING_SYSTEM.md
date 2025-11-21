# Meta-Learning System - Detailed Architecture

## 🎯 Core Concept
The system watches every task, learns what works, and automatically improves prompts for each model.

---

## 📦 Components

### 1. **Task Logger** (New File: `src/analytics/logger.py`)
**What it does:** Captures EVERYTHING during processing

**Integration points:**
```python
# In orchestrator.py - after enhancement
await logger.log_enhancement(
    task_id=task_id,
    model="wan-2.5-edit",
    original_prompt=original_prompt,
    enhanced_prompt=enhanced_prompt,
    latency_ms=2300
)

# After generation
await logger.log_generation(
    task_id=task_id,
    model="wan-2.5-edit",
    image_url=result.url,
    generation_time_ms=12500
)

# After validation
await logger.log_validation(
    task_id=task_id,
    model="wan-2.5-edit",
    score=10,
    passed=True,
    issues=[],
    reasoning="Perfect match..."
)

# After winner selection
await logger.log_winner(
    task_id=task_id,
    winner="wan-2.5-edit",
    score=10,
    total_iterations=1
)
```

**Data captured:**
- Task ID + timestamp
- Original Greek prompt
- Enhanced prompts (both models)
- Generation results + URLs
- Validation scores + reasoning
- Winner selection
- Processing times
- Iterations needed

---

### 2. **Database** (PostgreSQL on Railway)

**Schema:**
```sql
CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    clickup_task_id VARCHAR(50),
    original_prompt TEXT,
    created_at TIMESTAMP,
    winner_model VARCHAR(50),
    total_iterations INT,
    processing_time_ms INT
);

CREATE TABLE attempts (
    id SERIAL PRIMARY KEY,
    task_id INT REFERENCES tasks(id),
    model_name VARCHAR(50),
    enhanced_prompt TEXT,
    enhanced_prompt_length INT,
    image_url TEXT,
    validation_score INT,
    validation_passed BOOLEAN,
    validation_issues JSONB,
    validation_reasoning TEXT,
    was_selected BOOLEAN,
    generation_time_ms INT,
    created_at TIMESTAMP
);

CREATE TABLE insights (
    id SERIAL PRIMARY KEY,
    insight_type VARCHAR(50), -- 'prompt_pattern', 'model_strength', 'failure_mode'
    model_name VARCHAR(50),
    description TEXT,
    confidence_score FLOAT,
    tasks_analyzed INT,
    example_task_ids TEXT[],
    created_at TIMESTAMP,
    applied BOOLEAN DEFAULT FALSE
);

CREATE TABLE prompt_versions (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(50),
    version INT,
    prompt_template TEXT,
    activation_text TEXT,
    research_text TEXT,
    a_b_test_score FLOAT,
    tasks_tested INT,
    is_active BOOLEAN,
    created_at TIMESTAMP
);
```

---

### 3. **Analyzer** (New File: `src/analytics/analyzer.py`)

**Runs:** Every 50 tasks (scheduled job)

**What it does:** Sends data to Claude for pattern analysis

```python
class PatternAnalyzer:
    async def analyze_recent_tasks(self, task_count=50):
        """
        Pull last 50 tasks from DB
        Format for Claude
        Get insights
        """
        
        tasks = await self.db.get_recent_tasks(limit=50)
        
        # Build prompt for Claude
        prompt = f"""
        Analyze these {len(tasks)} image editing tasks.
        
        DATA:
        {self._format_tasks(tasks)}
        
        Find patterns:
        1. Which prompts lead to high scores for each model?
        2. What causes failures?
        3. Optimal prompt length per model?
        4. Greek text handling strategies?
        5. Model-specific strengths/weaknesses?
        
        Return JSON:
        {{
          "patterns": [...],
          "model_insights": {{
            "wan-2.5-edit": {{...}},
            "nano-banana": {{...}}
          }},
          "recommendations": [...]
        }}
        """
        
        response = await self.claude.analyze(prompt)
        insights = json.loads(response)
        
        # Save to DB
        await self.db.save_insights(insights)
        
        return insights
```

---

### 4. **Prompt Generator** (New File: `src/analytics/generator.py`)

**Runs:** After analyzer finds patterns

**What it does:** Creates new prompt templates

```python
class PromptGenerator:
    async def generate_improved_prompts(self, insights: dict):
        """
        Takes insights from analyzer
        Generates new enhancement templates
        """
        
        prompt = f"""
        Based on these insights:
        {json.dumps(insights, indent=2)}
        
        Generate improved prompt templates for:
        1. wan-2.5-edit enhancement
        2. nano-banana enhancement
        
        Keep structure similar to current templates.
        Incorporate successful patterns.
        Avoid failure modes.
        
        Return JSON with new templates.
        """
        
        response = await self.claude.generate(prompt)
        new_prompts = json.loads(response)
        
        # Save as new version
        await self.db.save_prompt_version(
            model="wan-2.5-edit",
            version=self.db.get_next_version("wan-2.5-edit"),
            template=new_prompts["wan-2.5-edit"],
            is_active=False  # Not active until tested
        )
        
        return new_prompts
```

---

### 5. **A/B Validator** (New File: `src/analytics/validator.py`)

**Runs:** After new prompts generated

**What it does:** Tests old vs new prompts

```python
class ABValidator:
    async def test_prompt_versions(self, model_name: str):
        """
        Next 20 tasks:
        - 10 use old prompts
        - 10 use new prompts
        Compare results
        """
        
        self.ab_test_active = True
        self.ab_test_config = {
            "model": model_name,
            "old_version": 1,
            "new_version": 2,
            "tasks_per_version": 10,
            "results": {"old": [], "new": []}
        }
        
        # Orchestrator checks this flag
        # Randomly picks version for each task
        
        # After 20 tasks:
        old_avg = mean([r.score for r in results["old"]])
        new_avg = mean([r.score for r in results["new"]])
        
        improvement = (new_avg - old_avg) / old_avg
        
        if improvement > 0.10:  # 10% better
            await self.activate_new_version(model_name, version=2)
            return {"status": "adopted", "improvement": improvement}
        else:
            return {"status": "rejected", "improvement": improvement}
```

---

### 6. **Config Updater** (New File: `src/analytics/updater.py`)

**Runs:** After A/B test passes

**What it does:** Updates config files

```python
class ConfigUpdater:
    async def update_deep_research(self, model: str, new_content: dict):
        """
        Update config/deep_research/{model}/
        - activation.txt
        - research.md
        """
        
        model_dir = Path(f"config/deep_research/{model}")
        
        # Backup old version
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = model_dir / f"backup_{timestamp}"
        backup_dir.mkdir()
        
        shutil.copy(
            model_dir / "activation.txt",
            backup_dir / "activation.txt"
        )
        shutil.copy(
            model_dir / "research.md",
            backup_dir / "research.md"
        )
        
        # Write new version
        with open(model_dir / "activation.txt", "w") as f:
            f.write(new_content["activation"])
        
        with open(model_dir / "research.md", "w") as f:
            f.write(new_content["research"])
        
        # Log change
        await self.db.log_config_update(
            model=model,
            backup_path=str(backup_dir),
            changes=new_content["summary"]
        )
```

---

## 🔄 Integration with Current System

### **Changes to `orchestrator.py`:**

```python
from analytics.logger import TaskLogger
from analytics.validator import ABValidator

class EditOrchestrator:
    def __init__(self):
        # Existing code...
        self.logger = TaskLogger(db)
        self.ab_validator = ABValidator(db)
    
    async def process_edit(self, task_id: str, ...):
        # Log task start
        await self.logger.log_task_start(task_id, original_prompt)
        
        try:
            # Existing enhancement code...
            enhanced = await self.enhance_prompt(...)
            
            # Log enhancement
            await self.logger.log_enhancement(
                task_id, model, original_prompt, enhanced
            )
            
            # Check if A/B test active
            if self.ab_validator.is_testing(model):
                version = self.ab_validator.get_test_version()
                enhanced = await self.enhance_with_version(
                    original_prompt, model, version
                )
            
            # Existing generation code...
            result = await self.generate(...)
            await self.logger.log_generation(task_id, model, result)
            
            # Existing validation code...
            validation = await self.validate(...)
            await self.logger.log_validation(task_id, model, validation)
            
            # Existing winner selection...
            winner = self.select_best(...)
            await self.logger.log_winner(task_id, winner, score)
            
        except Exception as e:
            await self.logger.log_error(task_id, str(e))
            raise
```

---

## 📅 Scheduled Jobs

**New File:** `src/analytics/scheduler.py`

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

# Every 50 tasks (check every hour)
@scheduler.scheduled_job('interval', hours=1)
async def check_for_analysis():
    task_count = await db.get_task_count_since_last_analysis()
    if task_count >= 50:
        await analyzer.analyze_recent_tasks()
        await generator.generate_improved_prompts()
        await validator.start_ab_test()

# Every day at 3am - cleanup old data
@scheduler.scheduled_job('cron', hour=3)
async def cleanup_old_data():
    await db.cleanup_tasks_older_than(days=90)

scheduler.start()
```

---

## 🚀 Deployment

**Railway Configuration:**

1. **Add PostgreSQL:**
   - Railway Dashboard → Add Database → PostgreSQL
   - Automatically adds `DATABASE_URL` env var

2. **Add to `requirements.txt`:**
   ```
   sqlalchemy==2.0.23
   asyncpg==0.29.0
   alembic==1.13.0
   apscheduler==3.10.4
   pandas==2.1.4
   ```

3. **Migration:**
   ```bash
   alembic init migrations
   alembic revision --autogenerate -m "Add analytics tables"
   alembic upgrade head
   ```

---

## 📊 Dashboard (Optional)

**New endpoint:** `GET /analytics`

Shows:
- Total tasks processed
- Model win rates
- Average scores over time
- Recent insights
- A/B test status
- Prompt version history

---

## 💰 Costs

- **PostgreSQL:** $5/month (Railway)
- **Claude API:** ~$10-15/month (analysis every 50 tasks)
- **Total:** $15-20/month

---

## 🎯 Implementation Order

1. **Week 1:** Database + Logger (silent logging)
2. **Week 2:** Analyzer (pattern detection)
3. **Week 3:** Generator + Validator (A/B testing)
4. **Week 4:** Updater + Scheduler (automation)

---

## 🔒 Safety Features

1. **Backup before updates:** All old prompts saved
2. **A/B testing required:** No blind deployments
3. **Rollback capability:** Can revert to any version
4. **Manual override:** Can disable automation anytime
5. **Confidence thresholds:** Only adopt if >10% improvement

---

## 📈 Success Metrics

Track:
- Validation scores trending up
- Iterations needed trending down
- Model selection becoming more consistent
- Processing time decreasing
- User satisfaction (tasks kept vs deleted)








graph TB
    subgraph "CURRENT SYSTEM"
        A[ClickUp Webhook] --> B[Orchestrator]
        B --> C[Enhancement<br/>Claude API]
        B --> D[Generation<br/>WaveSpeed]
        B --> E[Validation<br/>Claude API]
        C --> F[Select Best]
        D --> F
        E --> F
        F --> G[Upload to ClickUp]
    end

    subgraph "NEW: LEARNING LAYER"
        H[Task Logger<br/>Intercept Every Step]
        I[(PostgreSQL<br/>Railway)]
        J[Analyzer<br/>Claude API<br/>Every 50 tasks]
        K[Prompt Generator<br/>Claude API]
        L[A/B Validator]
        M[Config Updater]
        
        H -->|Write| I
        I -->|Read| J
        J -->|Insights| K
        K -->|New Prompts| L
        L -->|Test Results| M
        M -->|Update Files| N[config/deep_research/]
    end

    B -.->|Log Start| H
    C -.->|Log Enhancement| H
    D -.->|Log Generation| H
    E -.->|Log Validation| H
    F -.->|Log Winner| H
    G -.->|Log Complete| H

    style H fill:#ff6b6b
    style I fill:#4ecdc4
    style J fill:#ffe66d
    style K fill:#ffe66d
    style L fill:#95e1d3
    style M fill:#95e1d3
    style N fill:#f38181