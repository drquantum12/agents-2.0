# Guided Learning Agent - Quick Reference

## 🎯 Quick Start

### Run the Agent
```python
from app.agents.core_agent import run_agent

response = run_agent(
    user={"_id": "user123", "name": "Alice"},
    query="Teach me about photosynthesis",
    session_id="session_abc"
)
```

### API Call
```bash
curl -X POST http://localhost:8000/agent/query \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "Teach me about the water cycle"}'
```

## 📊 Agent State Fields

| Field | Type | Purpose | Example |
|-------|------|---------|---------|
| `query` | str | User's initial question | "Teach me about photosynthesis" |
| `user` | dict | User information | `{"_id": "123", "name": "Alice"}` |
| `messages` | list | Conversation history | `[HumanMessage(...), AIMessage(...)]` |
| `topic` | str | Refined lesson topic | "Photosynthesis in Plants" |
| `lesson_plan` | list[str] | Learning steps | `["Intro", "Chlorophyll", ...]` |
| `lesson_step` | int | Current step (1-indexed) | `3` |
| `quiz_mode` | bool | Quiz mode flag | `False` |
| `knowledge_gaps` | list[str] | Struggled concepts | `["ATP synthesis"]` |
| `last_action` | str | Workflow state | `"proceed"` / `"re-explain"` |
| `session_id` | str | Session identifier | `"session_abc"` |

## 🔄 Workflow States

```
┌─────────────┐
│   START     │
└──────┬──────┘
       ↓
┌─────────────┐
│ plan_lesson │ ← Creates lesson plan
└──────┬──────┘
       ↓
┌─────────────────────┐
│ generate_explanation│ ← Explains current step + asks question
└──────┬──────────────┘
       ↓
  [User Response]
       ↓
┌─────────────────┐
│ evaluate_response│ ← Checks understanding
└──────┬──────────┘
       ↓
   ┌───┴───┐
   │       │
proceed  re-explain
   │       │
   ↓       └──┐
Next Step     │
   │          ↓
   ↓    Clarify Current
  ...         │
   │          │
   └──────────┘
       ↓
  All Steps Done
       ↓
┌─────────────┐
│   reflect   │ ← Identifies knowledge gaps
└──────┬──────┘
       ↓
┌─────────────┐
│     END     │
└─────────────┘
```

## 🎨 Node Functions

### 1️⃣ plan_lesson
**Input**: User's query  
**LLM Tool**: `LessonPlanSchema`  
**Output**: Topic + lesson steps  
**Example**:
```python
{
    "topic": "Photosynthesis",
    "lesson_plan": [
        "What is photosynthesis and why it matters",
        "Key components: chloroplasts and chlorophyll",
        "The chemical equation",
        "Light-dependent vs light-independent reactions",
        "Real-world applications"
    ],
    "lesson_step": 1
}
```

### 2️⃣ generate_explanation
**Input**: Current lesson step  
**LLM Tool**: None (direct generation)  
**Output**: Explanation + question  
**Example**:
```
"Let's explore what photosynthesis is! Think of it as a plant's 
kitchen where sunlight is the energy source. Plants use this 
energy to convert water and carbon dioxide into glucose (food) 
and oxygen.

Here's a question to check your understanding: Why do you think 
plants need sunlight for this process?"
```

### 3️⃣ evaluate_response
**Input**: User's answer  
**LLM Tool**: `EvaluationSchema`  
**Output**: Action + feedback  
**Example** (proceed):
```python
{
    "action": "proceed",
    "feedback": "Great! You understand that sunlight provides energy.",
    "understanding_level": 8
}
```
**Example** (re-explain):
```python
{
    "action": "re-explain",
    "feedback": "Let me clarify: sunlight is the energy source, not food itself...",
    "understanding_level": 4
}
```

### 4️⃣ reflect_on_knowledge_gaps
**Input**: Conversation history  
**LLM Tool**: None (direct generation)  
**Output**: Knowledge gaps list  
**Example**:
```python
{
    "knowledge_gaps": [
        "light-dependent reactions",
        "ATP synthesis mechanism"
    ]
}
```

## 🔀 Routing Logic

```python
if last_action == 'planned':
    → generate_explanation  # Start first step

if last_action == 'explained':
    → end  # Wait for user response

if last_action == 're-explain':
    → generate_explanation  # Clarify current step

if last_action == 'proceed':
    if lesson_step > len(lesson_plan):
        → reflect  # All steps complete
    else:
        → generate_explanation  # Next step
```

## 📝 Prompts Overview

| Prompt | Purpose | Key Instructions |
|--------|---------|------------------|
| `LESSON_PLANNER_PROMPT` | Create lesson plan | Break topic into progressive steps |
| `TUTOR_EXPLANATION_PROMPT` | Explain concepts | Use analogies, ask questions |
| `EVALUATOR_PROMPT` | Assess understanding | Decide proceed vs re-explain |
| `REFLECTION_PROMPT` | Identify gaps | Analyze conversation for struggles |

## 🗄️ MongoDB Collections

### guided_learning_agent_checkpoints
**Purpose**: State persistence  
**Structure**:
```json
{
    "thread_id": "session_abc",
    "checkpoint": {
        "query": "...",
        "topic": "...",
        "lesson_step": 3,
        "messages": [...],
        ...
    },
    "metadata": {...}
}
```

### sessions
**Purpose**: Session metadata  
**Structure**:
```json
{
    "session_id": "device_session_id_user123",
    "created_at": "2025-12-07T09:00:00Z"
}
```

## ⚙️ Configuration

### Environment Variables
```bash
MONGODB_CONNECTION_STRING=mongodb://localhost:27017/neurosattva
GOOGLE_API_KEY=your_gemini_api_key
```

### Constants
```python
MAX_STEPS = 5  # Maximum lesson steps
```

## 🧪 Testing

### Structure Test (No DB required)
```bash
python test_agent_structure.py
```

### Full Test (Requires DB + API key)
```bash
python test_guided_agent.py
```

## 🐛 Debugging

### Enable Logging
```python
import logging
logging.basicConfig(level=logging.INFO)
```

### Check State in MongoDB
```javascript
// In MongoDB shell
db.guided_learning_agent_checkpoints.find({"thread_id": "session_abc"})
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| No tool calls | Model doesn't support function calling | Use gemini-1.5-pro or later |
| State not persisting | MongoDB connection issue | Check connection string |
| Infinite loop | Routing logic error | Check `last_action` updates |

## 📚 Documentation Files

- **Architecture**: `GUIDED_LEARNING_ARCHITECTURE.md`
- **Migration**: `MIGRATION_GUIDE_GUIDED_LEARNING.md`
- **API Reference**: `API_REFERENCE.md`
- **This File**: `QUICK_REFERENCE.md`

## 🚀 Example Conversation

**User**: "Teach me about the water cycle"

**Agent** (plan_lesson):  
"I've created a lesson plan for 'The Water Cycle' with 5 steps. Let's begin!"

**Agent** (generate_explanation):  
"Let's explore what the water cycle is! Imagine water on Earth as travelers on a never-ending journey... [explanation] ...

Here's a question: What do you think happens to water when the sun heats it?"

**User**: "It evaporates?"

**Agent** (evaluate_response → proceed):  
"Exactly right! Let's move to the next step..."

**Agent** (generate_explanation):  
"Now let's learn about condensation... [explanation]"

---

**Version**: 2.0  
**Last Updated**: December 2025
