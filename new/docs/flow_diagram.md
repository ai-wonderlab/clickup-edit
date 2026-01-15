# Image Editing Pipeline - Complete Flow Diagram

## High-Level Architecture

```mermaid
graph TD
    subgraph "Entry Point"
        A[ClickUp Webhook<br/>webhooks.py:319] -->|taskUpdated event| B{Signature Valid?}
        B -->|No| C[401 Unauthorized]
        B -->|Yes| D{Task Lock<br/>Available?}
        D -->|No| E[Already Processing]
        D -->|Yes| F[Acquire Lock]
    end

    subgraph "Task Validation"
        F --> G[Fetch Task from ClickUp]
        G --> H{Status = 'to do'?}
        H -->|No| I[Ignore - Wrong Status]
        H -->|Yes| J{AI Edit<br/>Checkbox?}
        J -->|No| K[Ignore - Not AI Task]
        J -->|Yes| L[TaskParser.parse]
    end

    subgraph "Task Parsing"
        L --> M[Extract Custom Fields]
        M --> N{Task Type?}
        N -->|Edit| O[SIMPLE_EDIT Flow]
        N -->|Creative| P[BRANDED_CREATIVE Flow]
    end

    subgraph "Attachment Processing"
        O --> Q[Download Attachments]
        P --> Q
        Q --> R[Convert to PNG]
        R --> S[Upload to ClickUp]
        S --> T[Get URLs]
    end

    subgraph "Brand Analysis (Optional)"
        T --> U{Brand Website<br/>Provided?}
        U -->|Yes| V[BrandAnalyzer.analyze]
        V --> W[Claude + Web Search]
        W --> X[Extract Brand Aesthetic]
        U -->|No| Y[Skip]
        X --> Z[Continue to Orchestrator]
        Y --> Z
    end

    subgraph "Main Processing"
        Z --> AA[Orchestrator.process_with_iterations]
    end

    subgraph "Iteration Loop (max 3)"
        AA --> AB[PHASE 1: Enhancement]
        AB --> AC[PromptEnhancer.enhance_all_parallel]
        AC --> AD[Claude Sonnet 4.5<br/>+ Deep Research<br/>+ Fonts Guide]
        
        AD --> AE[PHASE 2: Generation]
        AE --> AF[ImageGenerator.generate_all_parallel]
        AF --> AG[WaveSpeed API<br/>nano-banana-pro-edit]
        
        AG --> AH[PHASE 3: Validation]
        AH --> AI[Validator.validate_all_parallel]
        AI --> AJ[Claude Sonnet 4.5<br/>+ Validation Prompt]
        
        AJ --> AK{Score >= 8?}
        AK -->|Yes| AL[SUCCESS!]
        AK -->|No| AM{Iteration < 3?}
        AM -->|Yes| AN[PHASE 5: Refinement]
        AN --> AO[Refiner.refine_with_feedback]
        AO --> AB
        AM -->|No| AP{Can Break Down?}
    end

    subgraph "Sequential Mode"
        AP -->|Yes| AQ[Parse into Steps]
        AQ --> AR[Execute Sequential]
        AR --> AS[Step 1: Enhance → Generate → Validate]
        AS --> AT{Step Passed?}
        AT -->|Yes| AU[Step 2...]
        AT -->|No| AV{Attempt < 2?}
        AV -->|Yes| AS
        AV -->|No| AW[Sequential Failed]
        AU --> AX[Final Step]
        AX --> AY{All Passed?}
        AY -->|Yes| AL
        AY -->|No| AW
    end

    subgraph "Hybrid Fallback"
        AP -->|No| AZ[HybridFallback.trigger_human_review]
        AW --> AZ
        AZ --> BA[Update ClickUp Status = 'blocked']
        BA --> BB[Add Comment with Issues]
    end

    subgraph "Success Path"
        AL --> BC[Upload Final Image]
        BC --> BD[Update Status = 'complete']
        BD --> BE[Add Success Comment]
    end

    subgraph "Cleanup"
        BE --> BF[Uncheck AI Edit Checkbox]
        BB --> BF
        BF --> BG[Release Task Lock]
    end
```

## Detailed Phase Breakdown

### PHASE 1: Prompt Enhancement

```mermaid
graph LR
    subgraph "Enhancement Flow"
        A[Original Prompt] --> B[PromptEnhancer]
        B --> C{For Each Model}
        C --> D[Load Deep Research]
        D --> E[activation.txt + research.md]
        E --> F[Build System Prompt]
        F --> G[Add Fonts Guide]
        G --> H[Build User Prompt]
        H --> I[Add Images as Base64]
        I --> J[Call Claude Sonnet 4.5]
        J --> K[Enhanced Prompt]
    end
```

### PHASE 2: Image Generation

```mermaid
graph LR
    subgraph "Generation Flow"
        A[Enhanced Prompts] --> B[ImageGenerator]
        B --> C{For Each Model}
        C --> D[Build WaveSpeed Payload]
        D --> E[Submit Task]
        E --> F[Poll for Result]
        F --> G[Download Image]
        G --> H[GeneratedImage]
    end
```

### PHASE 3: Validation

```mermaid
graph LR
    subgraph "Validation Flow"
        A[Generated Images] --> B[Validator]
        B --> C{For Each Image}
        C --> D{Task Type?}
        D -->|SIMPLE_EDIT| E[validation_prompt.txt]
        D -->|BRANDED_CREATIVE| F[validation_branded_creative.txt]
        E --> G[Inject Fonts Guide]
        F --> G
        G --> H[Build Messages]
        H --> I[Add Original + Edited Images]
        I --> J[Call Claude Sonnet 4.5]
        J --> K[Parse JSON Response]
        K --> L{score >= 8?}
        L -->|Yes| M[PASS]
        L -->|No| N[FAIL]
    end
```

### Sequential Mode Detail

```mermaid
graph TD
    subgraph "Sequential Execution"
        A[Complex Request] --> B[parse_request_into_steps]
        B --> C[Split by 'και' / comma]
        C --> D[Add Preservation Clause]
        D --> E[Steps Array]
        
        E --> F[Step 1]
        F --> G[Full Pipeline]
        G --> H{Passed?}
        H -->|Yes| I[Use Output as Input]
        H -->|No| J{Attempt < 2?}
        J -->|Yes| G
        J -->|No| K[FAIL]
        
        I --> L[Step 2]
        L --> M[Full Pipeline]
        M --> N{Passed?}
        N -->|Yes| O[Continue...]
        N -->|No| P{Attempt < 2?}
        P -->|Yes| M
        P -->|No| K
        
        O --> Q[Final Step]
        Q --> R[Return Final Image]
    end
```

## Task Type Routing

```mermaid
graph TD
    subgraph "Task Type Decision"
        A[ParsedTask] --> B{task_type}
        B -->|Edit| C[SIMPLE_EDIT]
        B -->|Creative| D[BRANDED_CREATIVE]
        
        C --> E[Single Image Input]
        C --> F[validation_prompt.txt]
        C --> G[Simple Iteration Loop]
        
        D --> H[Multiple Images]
        D --> I[validation_branded_creative.txt]
        D --> J[Dimension Loop]
        
        J --> K[For Each Dimension]
        K --> L[First: Full Generation]
        L --> M[Subsequent: Adapt Previous]
    end
```

## Error Handling Flow

```mermaid
graph TD
    subgraph "Error Handling"
        A[Any Error] --> B{Error Type}
        B -->|AllEnhancementsFailed| C[Log + Continue]
        B -->|AllGenerationsFailed| D[Log + Continue]
        B -->|Validation Error| E[Log + Continue]
        B -->|Network Error| F[Retry with Backoff]
        B -->|Auth Error| G[Fail Immediately]
        
        C --> H{Last Iteration?}
        D --> H
        E --> H
        F --> I{Max Retries?}
        
        H -->|Yes| J[Hybrid Fallback]
        H -->|No| K[Next Iteration]
        I -->|Yes| J
        I -->|No| L[Retry]
    end
```

## Lock Management

```mermaid
graph TD
    subgraph "Task Locking"
        A[Webhook Received] --> B[acquire_task_lock]
        B --> C{Lock Exists?}
        C -->|Yes| D{Lock Stale?<br/>TTL > 1 hour}
        D -->|Yes| E[Clean + Create New]
        D -->|No| F[Reject Duplicate]
        C -->|No| G[Create Lock]
        
        G --> H[Process Task]
        E --> H
        
        H --> I{Success or Fail}
        I --> J[Finally Block]
        J --> K[release_task_lock]
        K --> L[Delete from Registry]
        
        subgraph "Periodic Cleanup"
            M[Every 100 Acquisitions]
            M --> N[cleanup_stale_locks]
            N --> O[Remove TTL > 1 hour]
        end
    end
```

