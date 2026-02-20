# Edge Case Handling: Mid-Lesson Topic Changes

## Overview

The Guided Learning Agent now includes **intelligent topic analysis** to handle edge cases where users:
- Change topics mid-lesson
- Ask off-topic questions
- Request clarifications about related concepts
- Get distracted and want to learn something else

## Problem Statement

**Scenario**: User is learning about "Photosynthesis" (Step 2 of 5) and suddenly asks:
- "Can you teach me about the solar system instead?"
- "What's the capital of France?"
- "Tell me about cellular respiration"
- "I don't understand, can you explain chlorophyll more?"

**Without edge case handling**: Agent would try to evaluate these as answers to the lesson question, leading to confusion.

**With edge case handling**: Agent intelligently detects intent and responds appropriately.

## Solution Architecture

### New Components

#### 1. **TopicAnalysisSchema** (`app/agents/schemas.py`)

```python
class TopicAnalysisSchema(BaseModel):
    is_related: bool  # Is query related to current topic?
    intent: Literal['answer', 'clarification', 'new_topic', 'off_topic_question']
    confidence: float  # 0.0 to 1.0
    suggested_action: Literal[
        'continue_lesson',      # User is answering
        'answer_and_continue',  # Answer their question, then continue
        'switch_topic',         # Start new lesson
        'politely_redirect'     # Redirect to current lesson
    ]
```

#### 2. **analyze_topic_context Node** (`app/agents/core_agent.py`)

New node that runs **before evaluation** to analyze user intent:

```python
def analyze_topic_context(state: AgentState) -> dict:
    """
    Analyzes if user's query is related to current lesson or represents a topic change.
    """
    # Analyzes:
    # - Current topic and step
    # - User's query
    # - Last agent message
    
    # Returns one of:
    # - context_analyzed: Continue to evaluation
    # - topic_switch: Start new lesson
    # - answered_question: Brief answer + continue
    # - redirected: Politely redirect to lesson
```

#### 3. **TOPIC_ANALYSIS_PROMPT** (`app/agents/prompts.py`)

Specialized prompt with examples:

```
Current topic: "Photosynthesis"
User query: "What about cellular respiration?"
→ is_related: True, intent: 'clarification', action: 'answer_and_continue'

Current topic: "Photosynthesis"
User query: "Can you teach me about the solar system instead?"
→ is_related: False, intent: 'new_topic', action: 'switch_topic'
```

### Updated Workflow

```
START → plan_lesson → generate_explanation
                            ↓
                      [User Response]
                            ↓
                    analyze_topic_context  ← NEW NODE
                            ↓
                    ┌───────┴───────┐
                    │               │
            context_analyzed    topic_switch
                    │               │
                    ↓               ↓
            evaluate_response   plan_lesson (new topic)
                    ↓
            {proceed/re-explain}
                    ↓
                   ...
```

## Handling Different Scenarios

### Scenario 1: User Answers Lesson Question ✅

**Context**:
- Topic: "Photosynthesis"
- Step: 2/5
- Last question: "Why do plants need sunlight?"

**User**: "Because they use it to make food"

**Analysis**:
```json
{
    "is_related": true,
    "intent": "answer",
    "suggested_action": "continue_lesson"
}
```

**Agent Action**: Proceeds to `evaluate_response` → evaluates answer → continues lesson

---

### Scenario 2: User Asks Related Question 🔄

**Context**:
- Topic: "Photosynthesis"
- Step: 2/5

**User**: "What about cellular respiration?"

**Analysis**:
```json
{
    "is_related": true,
    "intent": "clarification",
    "suggested_action": "answer_and_continue"
}
```

**Agent Response**:
```
"Great question! Cellular respiration is actually the opposite of photosynthesis - 
it breaks down glucose to release energy. We'll explore this more in step 4. 
For now, let's continue with step 2..."
```

**Agent Action**: Answers briefly → returns to `generate_explanation` for current step

---

### Scenario 3: User Wants New Topic 🔀

**Context**:
- Topic: "Photosynthesis"
- Step: 2/5

**User**: "Can you teach me about the solar system instead?"

**Analysis**:
```json
{
    "is_related": false,
    "intent": "new_topic",
    "suggested_action": "switch_topic"
}
```

**Agent Response**:
```
"I see you'd like to learn about something else. We've completed 1 out of 5 steps 
on 'Photosynthesis'. Let's start your new lesson!

I've created a lesson plan for 'The Solar System' with 5 steps. Let's begin!"
```

**Agent Action**: 
1. Saves progress message
2. Sets `context_switch=True` and `pending_topic="solar system"`
3. Routes to `plan_lesson` with new topic
4. Starts fresh lesson

---

### Scenario 4: Off-Topic Question 🚫

**Context**:
- Topic: "Photosynthesis"
- Step: 2/5

**User**: "What's the capital of France?"

**Analysis**:
```json
{
    "is_related": false,
    "intent": "off_topic_question",
    "suggested_action": "politely_redirect"
}
```

**Agent Response**:
```
"That's an interesting question! However, let's focus on completing our lesson 
on 'Photosynthesis' first. We're on step 2 of 5. Once we finish, I'd be happy 
to help with other topics!"
```

**Agent Action**: Politely redirects → ends turn → waits for user to continue lesson

---

## State Management

### New State Fields

```python
class AgentState(TypedDict):
    # ... existing fields ...
    context_switch: bool      # Flag indicating topic switch
    pending_topic: str        # New topic to learn (if switching)
```

### State Transitions

#### Normal Flow:
```
last_action: "explained" → "context_analyzed" → "proceed" → "explained"
```

#### Topic Switch Flow:
```
last_action: "explained" → "topic_switch" → "planned" → "explained"
context_switch: False → True → False
pending_topic: "" → "solar system" → ""
```

#### Answer Question Flow:
```
last_action: "explained" → "answered_question" → "explained"
```

#### Redirect Flow:
```
last_action: "explained" → "redirected" → (end turn)
```

## Implementation Details

### 1. Topic Analysis Logic

```python
# In analyze_topic_context node:

if suggested_action == 'switch_topic':
    # Save progress and switch
    return {
        "messages": [progress_message],
        "context_switch": True,
        "pending_topic": user_query,
        "last_action": "topic_switch"
    }

elif suggested_action == 'answer_and_continue':
    # Brief answer
    answer = llm.invoke(f"Briefly answer: {user_query}")
    return {
        "messages": [answer],
        "last_action": "answered_question"
    }

elif suggested_action == 'politely_redirect':
    # Redirect message
    return {
        "messages": [redirect_message],
        "last_action": "redirected"
    }

else:  # continue_lesson
    # Proceed to evaluation
    return {"last_action": "context_analyzed"}
```

### 2. Updated Routing

```python
def should_continue(state):
    last_action = state['last_action']
    
    if last_action == 'explained':
        return "analyze_topic"  # NEW: Analyze before evaluating
    
    if last_action == 'context_analyzed':
        return "evaluate_response"
    
    if last_action == 'topic_switch':
        return "plan_lesson"  # Start new lesson
    
    if last_action == 'answered_question':
        return "generate_explanation"  # Continue current step
    
    if last_action == 'redirected':
        return "end"  # Wait for user
    
    # ... other routing logic ...
```

### 3. Plan Lesson Enhancement

```python
def plan_lesson(state):
    # Check for topic switch
    context_switch = state.get('context_switch', False)
    pending_topic = state.get('pending_topic', '')
    
    # Use pending_topic if switching
    topic_to_plan = pending_topic if context_switch else state['query']
    
    # ... generate lesson plan ...
    
    return {
        "topic": topic,
        "lesson_plan": steps,
        "context_switch": False,  # Reset flag
        "pending_topic": ""       # Clear pending topic
    }
```

## Benefits

### 1. **Better User Experience**
- Users can naturally change topics
- Related questions are answered without disrupting flow
- Off-topic questions are handled gracefully

### 2. **Maintains Learning Context**
- Tracks progress before switching
- Can resume lessons later (via checkpointing)
- Knowledge gaps tracked across topics

### 3. **Intelligent Routing**
- LLM decides intent, not hard-coded rules
- Adapts to various phrasings
- Confidence scoring for uncertain cases

### 4. **Graceful Degradation**
- Falls back to continuing lesson on errors
- Logs all decisions for debugging
- Handles edge cases in edge cases!

## Testing Edge Cases

### Test 1: Mid-Lesson Topic Switch
```python
# Start lesson on photosynthesis
response1 = run_agent(user, "Teach me about photosynthesis", session_id)
# Step 1 explanation

# User responds to step 1
response2 = run_agent(user, "Plants use sunlight", session_id)
# Evaluation + Step 2 explanation

# User switches topic
response3 = run_agent(user, "Actually, teach me about the water cycle", session_id)
# Expected: Progress message + new lesson plan for water cycle
```

### Test 2: Related Question
```python
# During photosynthesis lesson
response = run_agent(user, "What about chlorophyll?", session_id)
# Expected: Brief answer about chlorophyll + continue current step
```

### Test 3: Off-Topic Question
```python
# During photosynthesis lesson
response = run_agent(user, "Who invented the telephone?", session_id)
# Expected: Polite redirect to current lesson
```

## Monitoring & Debugging

### Logs
```
INFO: Analyzing topic context for query: Can you teach me about...
INFO: Topic analysis: intent=new_topic, action=switch_topic, confidence=0.95
INFO: User wants to switch from 'Photosynthesis' to a new topic
INFO: Planning lesson for topic: the water cycle (topic switch)
```

### State Inspection
```javascript
// In MongoDB
db.guided_learning_agent_checkpoints.find({
    "thread_id": "session_123"
}).pretty()

// Check for:
// - context_switch: true/false
// - pending_topic: "..."
// - last_action: "topic_switch"
```

## Future Enhancements

### 1. **Resume Previous Lesson**
```
User: "Actually, let's go back to photosynthesis"
Agent: "Sure! We were on step 2 of 5. Let's continue..."
```

### 2. **Multi-Topic Learning Paths**
- Track multiple concurrent lessons
- Switch between topics seamlessly
- Recommend related topics

### 3. **Smart Interruptions**
- Detect if user is confused vs. curious
- Offer to pause lesson for deep dive
- Resume automatically after clarification

### 4. **Progress Persistence**
- Save incomplete lessons
- Show lesson history
- Resume from any point

## Configuration

### Sensitivity Tuning

Adjust topic analysis sensitivity in the prompt:

```python
# More lenient (allows more topic switches)
"If confidence < 0.7, default to 'continue_lesson'"

# More strict (fewer interruptions)
"Only switch topics if confidence > 0.9 and user explicitly says 'instead' or 'teach me about'"
```

### Custom Behaviors

```python
# In analyze_topic_context:

# Option 1: Always allow topic switches
if intent == 'new_topic':
    return switch_topic()

# Option 2: Require confirmation
if intent == 'new_topic':
    return ask_confirmation()

# Option 3: Finish current step first
if intent == 'new_topic' and lesson_step < len(lesson_plan):
    return suggest_finish_step()
```

## Summary

The edge case handling system provides:

✅ **Intelligent topic detection** using LLM analysis  
✅ **4 distinct user intents** (answer, clarification, new_topic, off_topic)  
✅ **4 handling strategies** (continue, answer_and_continue, switch, redirect)  
✅ **Seamless topic switching** with progress tracking  
✅ **Graceful handling** of off-topic questions  
✅ **Maintained context** across topic changes  
✅ **Comprehensive logging** for debugging  

The system makes the learning experience **natural and flexible** while maintaining **structure and progress tracking**.

---

**Last Updated**: December 7, 2025  
**Version**: 2.1  
**Feature**: Topic Analysis & Context Switching
