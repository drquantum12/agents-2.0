# Migration Guide: Guided Learning Agent Architecture

## Overview

This guide explains the migration from a simple Q&A agent to a sophisticated **Guided Learning Agent** using LangGraph, structured state management, and MongoDB persistence.

## What Changed?

### 1. **Core Agent Architecture** (`app/agents/core_agent.py`)

#### Before:
- Simple function-based agent
- Minimal state tracking
- Direct LLM calls without structured workflow

#### After:
- **LangGraph-based state machine** with 4 specialized nodes
- **Comprehensive state management** with 10 tracked fields
- **Conditional routing** between nodes based on learning progress
- **MongoDB checkpointing** for session persistence

### 2. **Agent State** (`AgentState`)

#### New Fields Added:
```python
lesson_plan: list[str]     # NEW: Structured lesson steps
last_action: str           # NEW: Tracks workflow state
session_id: str            # NEW: Explicit session tracking
```

#### Modified Fields:
```python
lesson_step: int           # ENHANCED: Now tracks progress through plan
topic: str                 # ENHANCED: Extracted from lesson plan
knowledge_gaps: list[str]  # ENHANCED: Populated by reflection node
```

### 3. **New Schemas** (`app/agents/schemas.py`)

#### Added:
```python
class EvaluationSchema(BaseModel):
    """Structured evaluation of user responses"""
    action: Literal['proceed', 're-explain']
    feedback: str
    understanding_level: int  # 1-10 rating
```

#### Enhanced:
```python
class LessonPlanSchema(BaseModel):
    """Now includes detailed docstrings and validation"""
    topic: str
    steps: list[str]  # Up to MAX_STEPS
```

### 4. **New Prompts** (`app/agents/prompts.py`)

#### Added 4 Specialized Prompts:
1. **`LESSON_PLANNER_PROMPT`**: Creates structured learning paths
2. **`TUTOR_EXPLANATION_PROMPT`**: Generates engaging explanations
3. **`EVALUATOR_PROMPT`**: Assesses understanding with empathy
4. **`REFLECTION_PROMPT`**: Identifies knowledge gaps

### 5. **Dependencies** (`requirements.txt`)

#### Added:
```
langgraph-checkpoint-mongodb==0.2.1
```

## How the New Agent Works

### Workflow Diagram

```
User Query: "Teach me about photosynthesis"
    ↓
┌─────────────────────┐
│  plan_lesson        │  Creates 5-step lesson plan
│  (Planning Node)    │  Sets topic, lesson_plan, lesson_step=1
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ generate_explanation│  Explains Step 1 + asks question
│ (Tutor Node)        │  "What do plants need for photosynthesis?"
└──────────┬──────────┘
           ↓
      [User responds]
           ↓
┌─────────────────────┐
│ evaluate_response   │  Assesses understanding
│ (Evaluator Node)    │  Returns: {action: 'proceed', feedback: '...'}
└──────────┬──────────┘
           ↓
    ┌──────┴──────┐
    │             │
 proceed      re-explain
    │             │
    ↓             ↓
Step 2      Clarify Step 1
    ↓             ↓
   ...      (back to generate_explanation)
    ↓
All steps complete
    ↓
┌─────────────────────┐
│ reflect             │  Identifies knowledge gaps
│ (Reflection Node)   │  Updates knowledge_gaps list
└──────────┬──────────┘
           ↓
          END
```

### Node Functions

#### 1. `plan_lesson(state) -> dict`
**Trigger**: First call with new topic  
**Input**: `state['query']`  
**LLM Call**: Uses `LessonPlanSchema` tool  
**Output**: 
```python
{
    "topic": "Photosynthesis",
    "lesson_plan": ["Step 1", "Step 2", ...],
    "lesson_step": 1,
    "last_action": "planned"
}
```

#### 2. `generate_explanation(state) -> dict`
**Trigger**: After planning OR after evaluation (proceed/re-explain)  
**Input**: `state['lesson_step']`, `state['lesson_plan']`  
**LLM Call**: Direct text generation  
**Output**:
```python
{
    "messages": [AIMessage(content="Explanation + Question")],
    "last_action": "explained"
}
```

#### 3. `evaluate_response(state) -> dict`
**Trigger**: After user responds to explanation  
**Input**: Last user message, last AI question  
**LLM Call**: Uses `EvaluationSchema` tool  
**Output** (if proceed):
```python
{
    "lesson_step": current_step + 1,
    "last_action": "proceed"
}
```
**Output** (if re-explain):
```python
{
    "messages": [AIMessage(content="Hint/clarification")],
    "last_action": "re-explain"
}
```

#### 4. `reflect_on_knowledge_gaps(state) -> dict`
**Trigger**: After all lesson steps complete  
**Input**: Conversation history, current gaps  
**LLM Call**: Direct text generation  
**Output**:
```python
{
    "knowledge_gaps": ["concept1", "concept2", ...]
}
```

### Conditional Routing (`should_continue`)

```python
def should_continue(state) -> Literal["generate_explanation", "evaluate_response", "reflect", "end"]:
    last_action = state['last_action']
    
    if last_action == 'planned':
        return "generate_explanation"  # Start first step
    
    if last_action == 'explained':
        return "end"  # Wait for user response (next turn)
    
    if last_action == 're-explain':
        return "generate_explanation"  # Clarify current step
    
    if last_action == 'proceed':
        if lesson_step > len(lesson_plan):
            return "reflect"  # All steps done
        else:
            return "generate_explanation"  # Next step
    
    return "end"
```

## Migration Steps for Developers

### Step 1: Update Dependencies
```bash
pip install langgraph-checkpoint-mongodb==0.2.1
```

### Step 2: Environment Variables
Ensure these are set:
```bash
MONGODB_CONNECTION_STRING=mongodb://...
GOOGLE_API_KEY=your_gemini_api_key
```

### Step 3: Database Collections
The agent will automatically create:
- `guided_learning_agent_checkpoints`: State persistence
- `sessions`: Session metadata (existing)

### Step 4: API Endpoint (No Changes Required!)
The existing `/agent/query` endpoint works as-is:
```python
@router.post("/agent/query")
async def agent(request: QueryRequest, user: User = Depends(get_current_user)):
    session_id = get_or_create_device_session_id(user_id=user["_id"])
    response = run_agent(user=user, query=request.query, session_id=session_id)
    return {"response": response}
```

### Step 5: Testing
Run the structure test:
```bash
python test_agent_structure.py
```

Run the full test (requires env vars):
```bash
python test_guided_agent.py
```

## Breaking Changes

### ⚠️ None!
The new agent is **backward compatible**. Existing API calls will work, but will now benefit from:
- Structured lesson planning
- Progressive learning steps
- Understanding evaluation
- Knowledge gap tracking

## New Capabilities

### 1. **Stateful Learning Sessions**
```python
# First call
response = run_agent(user, "Teach me about photosynthesis", session_id)
# Returns: Lesson plan + Step 1 explanation

# Second call (same session)
response = run_agent(user, "Plants use sunlight", session_id)
# Returns: Evaluation + Step 2 explanation
```

### 2. **Knowledge Gap Tracking**
```python
# After lesson completion, state contains:
state['knowledge_gaps'] = [
    "light-dependent reactions",
    "ATP synthesis"
]
# Can be used for personalized recommendations
```

### 3. **Adaptive Re-teaching**
If user shows confusion, agent automatically:
1. Detects via `EvaluationSchema`
2. Provides targeted hint
3. Re-explains concept
4. Asks simpler question

## Performance Considerations

### MongoDB Checkpointing
- **Pros**: Persistent state across server restarts
- **Cons**: Adds ~50-100ms per request
- **Optimization**: Use connection pooling (already configured)

### LLM Tool Calls
- **Lesson Planning**: 1 tool call (once per topic)
- **Evaluation**: 1 tool call per user response
- **Total**: ~2-3 tool calls per lesson step

### Recommended Limits
```python
MAX_STEPS = 5  # Current default
# For longer lessons, increase to 7-10
# For quick concepts, decrease to 3
```

## Rollback Plan

If issues arise, you can rollback by:

1. **Revert core_agent.py** to previous version
2. **Remove new prompts** from prompts.py
3. **Remove EvaluationSchema** from schemas.py
4. **Uninstall** langgraph-checkpoint-mongodb

The database collections are separate, so no data loss.

## Future Enhancements

### Planned Features
1. **Quiz Mode**: Formal assessments at lesson end
2. **Multi-session Learning Paths**: Track progress across topics
3. **Adaptive Difficulty**: Adjust based on user performance
4. **Visual Aids**: Generate diagrams for complex concepts
5. **Collaborative Learning**: Group sessions

### Extension Points
- Add custom nodes for specific domains (math, science, etc.)
- Integrate with external knowledge bases (RAG)
- Add voice/video support for explanations
- Implement spaced repetition for review

## Support

### Documentation
- Architecture: `GUIDED_LEARNING_ARCHITECTURE.md`
- API Reference: `API_REFERENCE.md`
- Project Overview: `PROJECT_OVERVIEW.md`

### Debugging
Enable detailed logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Check agent state:
```python
# In MongoDB
db.guided_learning_agent_checkpoints.find({"thread_id": "session_id"})
```

### Common Issues

**Issue**: "No tool calls in response"  
**Solution**: Ensure Gemini model supports function calling (gemini-1.5-pro or later)

**Issue**: "State not persisting"  
**Solution**: Verify MongoDB connection and checkpointer initialization

**Issue**: "Agent loops infinitely"  
**Solution**: Check `should_continue` logic and `last_action` updates

---

**Migration Date**: December 2025  
**Version**: 2.0  
**Contact**: Development Team
