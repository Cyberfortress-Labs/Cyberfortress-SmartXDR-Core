# Prompts Organization Guide

## Directory Structure

```
prompts/
├── system/          # Core system prompts (highest privilege, rarely changed)
└── instructions/    # Task-specific prompts (frequently tuned)
```

---

## `prompts/system/` – Core System Prompts

**Purpose:** Defines the identity, behavior, and core capabilities of SmartXDR AI
**Characteristics:**

* Highest privilege in the hierarchy
* Rarely modified (only for major changes)
* Defines “who the AI is” and “how it behaves”
* Applied globally across all features

### Files

#### 1. `base_system.json`

* **Role:** SmartXDR identity and ecosystem overview
* **Content:**

  * AI identity (“You are SmartXDR…”)
  * Lab architecture
  * Network topology (6 segments)
  * Device inventory and capabilities
  * MITRE ATT&CK knowledge
* **Used by:** All LLM calls
* **Update frequency:** Rare

#### 2. `rag_system.json`

* **Role:** RAG behavior rules
* **Content:**

  * Context interpretation guidelines
  * Language matching (EN/VI)
  * Source citation rules
  * Fallback behavior
* **Used by:** `LLMService.ask_rag()`
* **Update frequency:** Rare

#### 3. `rag_user_input.json`

* **Role:** Template for building RAG queries
* **Content:**

  * User input schema
  * Context injection structure
* **Used by:** `PromptBuilderService.build_rag_user_input()`
* **Update frequency:** Rare

#### 4. `system_prompt_template.md`

* **Role:** Documentation and guidance template
* **Content:** Examples and structure reference
* **Update frequency:** As needed

---

## `prompts/instructions/` – Task-Specific Prompts

**Purpose:** Provides focused guidance for specific tasks (alert analysis, IOC enrichment, etc.)
**Characteristics:**

* Task-oriented
* Frequently tuned to improve output
* Easy to A/B test
* Customizable per use case

### Files

#### 1. `alert_summary.json`

* **Task:** Summarize alerts from ElastAlert2, Kibana, and ML
* **Used by:** Email reports, Telegram `/summary`
* **Output:** Security overview, top issues, recommended actions
* **Update frequency:** Medium

#### 2. `alert_ai_analysis.json` (moved from system/)

* **Task:** AI risk scoring and attack-pattern analysis
* **Used by:** `AlertSummarizationService._generate_ai_analysis()`
* **Output:** Threat assessment, key actions, MITRE techniques
* **Update frequency:** High

#### 3. `sumlogs_analysis.json` (moved from system/)

* **Task:** Analyze ML-classified logs
* **Used by:** Telegram `/sumlogs`
* **Output:** Top dangerous logs, recommendations, MITRE mapping
* **Update frequency:** High

#### 4. `ioc_enrichment.json`

* **Task:** Explain IntelOwl IOC enrichment results
* **Used by:** IOC enrichment endpoints
* **Output:** Risk rating, findings, actions
* **Update frequency:** Medium

#### 5. `playbook_selection.json`

* **Task:** Recommend response playbooks
* **Used by:** SOAR automation
* **Status:** Empty (TODO)

#### 6. `severity_scoring.json`

* **Task:** Score incident severity
* **Used by:** Triage workflow
* **Status:** Empty (TODO)

---

## Reorganization Changes (Dec 10, 2025)

### Moved from `system/` to `instructions/`

1. **`alert_ai_analysis.json`**

   * Reason: Task-specific, tuned frequently
   * Old: `prompts/system/alert_ai_analysis.json`
   * New: `prompts/instructions/alert_ai_analysis.json`
   * Updated reference: `alert_summarization_service.py`

2. **`sumlogs_analysis.json`**

   * Reason: Task-specific, tuned based on log types
   * Old: `prompts/system/sumlogs_analysis.json`
   * New: `prompts/instructions/sumlogs_analysis.json`
   * Updated reference: `telegram_middleware_service.py`

### Removed

* `triage.json` (empty, removed)

### Renamed

* `system_promt_template.md` → `system_prompt_template.md`

---

## Hierarchy Logic

```
┌─────────────────────────────────────┐
│     prompts/system/                 │  Highest privilege
│  (Core identity & behavior)         │  Rarely changed
│  - base_system.json                 │  Defines “who the AI is”
│  - rag_system.json                  │
│  - rag_user_input.json              │
└─────────────────────────────────────┘
              ↓ Used by all tasks
┌─────────────────────────────────────┐
│   prompts/instructions/             │  Task-specific
│  (Task-focused prompts)             │  Frequently tuned
│  - alert_summary.json               │  Defines “how to do X”
│  - alert_ai_analysis.json           │
│  - sumlogs_analysis.json            │
│  - ioc_enrichment.json              │
│  - playbook_selection.json          │
│  - severity_scoring.json            │
└─────────────────────────────────────┘
```

---

## When to Edit What?

### Edit `prompts/system/` when:

* Ecosystem or topology changes
* Core AI behavior needs redesign
* RAG logic changes
* Not for quality tuning
* Not for task-specific output

### Edit `prompts/instructions/` when:

* Improve quality for a specific task
* Add/remove task requirements
* A/B testing new instructions
* Customize for special use cases
* Tune severity, language, formatting

---

## Code Usage Pattern

```python
# System prompts
from app.services.prompt_builder_service import PromptBuilderService
builder = PromptBuilderService()
system_prompt = builder.build_system_prompt()
rag_prompt = builder.build_rag_prompt()

# Instruction prompts
import json

# Alert AI analysis
with open("prompts/instructions/alert_ai_analysis.json") as f:
    prompt_data = json.load(f)
    system_prompt = prompt_data["system_prompt"]
    user_template = prompt_data["user_prompt_template"]

# ML logs analysis
with open("prompts/instructions/sumlogs_analysis.json") as f:
    prompt_data = json.load(f)
    # ...
```

---

## Best Practices

1. Maintain versioning (`last_updated`)
2. Always provide fallback prompts
3. Test prompts before committing
4. Document changes in commit messages
5. Keep old versions for A/B testing
6. Monitor token usage when updating prompts

