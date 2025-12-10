# Prompts Organization Guide

## 📁 Directory Structure

```
prompts/
├── system/          # Core system prompts (quyền cao nhất, ít thay đổi)
└── instructions/    # Task-specific prompts (thường xuyên tune)
```

---

## 🎯 `prompts/system/` - Core System Prompts

**Purpose:** Định nghĩa identity, behavior, và core capabilities của SmartXDR AI  
**Characteristics:**
- Quyền cao nhất trong hierarchy
- Ít thay đổi (chỉ khi có major updates)
- Định nghĩa "AI là ai" và "AI hoạt động thế nào"
- Áp dụng cho toàn bộ hệ thống

### Files:

#### 1. `base_system.json`
- **Role:** SmartXDR identity & ecosystem overview
- **Content:**
  - AI identity: "You are SmartXDR..."
  - Lab environment architecture
  - Network topology (6 segments)
  - Device inventory & capabilities
  - MITRE ATT&CK framework
- **Used by:** All LLM calls (foundation)
- **Update frequency:** Rare (only when ecosystem changes)

#### 2. `rag_system.json`
- **Role:** RAG behavior rules
- **Content:**
  - Context interpretation guidelines
  - Language matching (EN/VI)
  - Source citation rules
  - Fallback behavior
- **Used by:** `LLMService.ask_rag()`
- **Update frequency:** Rare (only when RAG logic changes)

#### 3. `rag_user_input.json`
- **Role:** RAG query template
- **Content:**
  - User input format
  - Context injection template
- **Used by:** `PromptBuilderService.build_rag_user_input()`
- **Update frequency:** Rare

#### 4. `system_prompt_template.md`
- **Role:** Documentation & template reference
- **Content:** Examples and structure guide
- **Update frequency:** As needed

---

## 📝 `prompts/instructions/` - Task-Specific Prompts

**Purpose:** Hướng dẫn cụ thể cho từng task (alert analysis, IOC enrichment, v.v.)  
**Characteristics:**
- Task-focused instructions
- Thường xuyên tune để cải thiện output quality
- Dễ dàng A/B test
- Có thể customize theo use case

### Files:

#### 1. `alert_summary.json`
- **Task:** Tóm tắt alerts từ ElastAlert2, Kibana, ML
- **Used by:** Email reporting, Telegram `/summary`
- **Output:** Tổng quan tình hình bảo mật + top issues + actions
- **Update frequency:** Medium (tune based on feedback)

#### 2. `alert_ai_analysis.json` ⬅️ Moved from system/
- **Task:** AI phân tích risk score + attack patterns
- **Used by:** `AlertSummarizationService._generate_ai_analysis()`
- **Output:** Threat assessment + priority actions + MITRE
- **Update frequency:** High (tune recommendations)

#### 3. `sumlogs_analysis.json` ⬅️ Moved from system/
- **Task:** Phân tích ML-classified logs
- **Used by:** Telegram `/sumlogs` command
- **Output:** Top dangerous logs + recommendations + MITRE
- **Update frequency:** High (tune based on log types)

#### 4. `ioc_enrichment.json`
- **Task:** Giải thích IntelOwl IOC analysis
- **Used by:** IOC enrichment endpoints
- **Output:** Risk assessment + findings + actions
- **Update frequency:** Medium

#### 5. `playbook_selection.json`
- **Task:** Recommend response playbooks
- **Used by:** SOAR automation
- **Status:** ⚠️ Empty (TODO)

#### 6. `severity_scoring.json`
- **Task:** Score severity của incidents
- **Used by:** Triage workflow
- **Status:** ⚠️ Empty (TODO)

---

## 🔄 Reorganization Changes (Dec 10, 2025)

### Moved from `system/` to `instructions/`:

1. **`alert_ai_analysis.json`**
   - Reason: Task-specific, thường xuyên tune recommendations
   - Old path: `prompts/system/alert_ai_analysis.json`
   - New path: `prompts/instructions/alert_ai_analysis.json`
   - Updated: `app/services/alert_summarization_service.py`

2. **`sumlogs_analysis.json`**
   - Reason: Task-specific, tune theo log types
   - Old path: `prompts/system/sumlogs_analysis.json`
   - New path: `prompts/instructions/sumlogs_analysis.json`
   - Updated: `app/services/telegram_middleware_service.py`

### Removed:

- **`triage.json`** - Empty file (removed)

### Renamed:

- **`system_promt_template.md`** → `system_prompt_template.md` (fixed typo)

---

## 📊 Hierarchy Logic

```
┌─────────────────────────────────────┐
│     prompts/system/                 │  ← Quyền cao nhất
│  (Core identity & behavior)         │     Ít thay đổi
│  - base_system.json                 │     Define "who AI is"
│  - rag_system.json                  │
│  - rag_user_input.json              │
└─────────────────────────────────────┘
              ↓ Uses
┌─────────────────────────────────────┐
│   prompts/instructions/             │  ← Task-specific
│  (Task-focused prompts)             │     Thường xuyên tune
│  - alert_summary.json               │     Define "how to do X"
│  - alert_ai_analysis.json           │
│  - sumlogs_analysis.json            │
│  - ioc_enrichment.json              │
│  - playbook_selection.json          │
│  - severity_scoring.json            │
└─────────────────────────────────────┘
```

---

## 🎯 When to Edit Which?

### Edit `prompts/system/` when:
- ✅ Ecosystem topology changes (new devices, IPs)
- ✅ Core AI behavior needs adjustment
- ✅ RAG logic changes
- ❌ NOT for output quality tuning
- ❌ NOT for task-specific improvements

### Edit `prompts/instructions/` when:
- ✅ Muốn improve output quality của 1 task cụ thể
- ✅ Thêm/bớt requirements cho task
- ✅ A/B test different prompts
- ✅ Customize cho specific use cases
- ✅ Tune recommendations, format, language

---

## 🔧 Code Usage Pattern

```python
# System prompts - loaded via PromptBuilderService
from app.services.prompt_builder_service import PromptBuilderService
builder = PromptBuilderService()
system_prompt = builder.build_system_prompt()  # Uses prompts/system/base_system.json
rag_prompt = builder.build_rag_prompt()        # Uses prompts/system/rag_system.json

# Instruction prompts - loaded directly per task
import json

# Example: Alert AI analysis
with open("prompts/instructions/alert_ai_analysis.json", 'r') as f:
    prompt_data = json.load(f)
    system_prompt = prompt_data['system_prompt']
    user_template = prompt_data['user_prompt_template']

# Example: ML logs analysis
with open("prompts/instructions/sumlogs_analysis.json", 'r') as f:
    prompt_data = json.load(f)
    # Use prompt_data...
```

---

## 📈 Best Practices

1. **Version tracking:** Update `last_updated` field khi chỉnh sửa
2. **Fallback:** Always có fallback prompt trong code
3. **Testing:** Test prompts trước khi commit
4. **Documentation:** Document changes trong commit message
5. **A/B Testing:** Keep old versions để compare
6. **Token optimization:** Monitor token usage sau khi update prompts

---

## 🚀 Future Enhancements

- [ ] Add prompt versioning system (v1, v2, v3)
- [ ] Create prompt effectiveness metrics
- [ ] Build A/B testing framework
- [ ] Add JSON schema validation
- [ ] Create prompt library với examples
- [ ] Add multi-language support templates

---

**Last Updated:** December 10, 2025  
**Maintainer:** SmartXDR Team
