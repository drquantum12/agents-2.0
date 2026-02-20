# Guided Learning Agent Architecture

## Overview

This project implements a **Guided Learning Agent** using **LangGraph** for orchestration, **Gemini API** for reasoning, and **MongoDB** for state persistence and memory. The agent provides a structured, adaptive learning experience that guides students through topics step-by-step.

## Architecture Components

### 1. Technology Stack

- **LangGraph**: Orchestrates the agent workflow with stateful graph-based execution
- **Gemini API**: Provides AI reasoning for lesson planning, explanations, and evaluation
- **MongoDB**: Handles both short-term (checkpointing) and long-term (knowledge gaps) memory
- **FastAPI**: Serves the agent endpoints
- **Pydantic**: Ensures structured outputs from the LLM

### 2. Agent State (`AgentState`)

The state is the shared data structure that passes between nodes in the graph:

```python
class AgentState(TypedDict):
    query: str                    # User's question or topic
    user: dict                    # User information
    messages: list[BaseMessage]   # Conversation history
    topic: str                    # Main lesson topic
    lesson_plan: list[str]        # List of lesson steps
    lesson_step: int              # Current step number (1-indexed)
    quiz_mode: bool               # Flag for quiz mode (future feature)
    knowledge_gaps: list[str]     # Topics user struggled with
    last_action: str              # Last action: 'proceed', 're-explain', 'planned', etc.
    session_id: str               # Session identifier
```

### 3. Agent Nodes

The agent consists of four main nodes, each with a specific responsibility:

#### A. **Planning Node** (`plan_lesson`)

**Purpose**: Generates a structured lesson plan when a new topic is introduced.

**Process**:
1. Takes the user's query/topic
2. Calls Gemini with `LESSON_PLANNER_PROMPT`
3. Uses `LessonPlanSchema` tool for structured output
4. Returns a list of progressive learning steps

**Output**: Updates state with `topic`, `lesson_plan`, and sets `lesson_step` to 1

#### B. **Explanation Node** (`generate_explanation`)

**Purpose**: Generates clear explanations for the current lesson step.

**Process**:
1. Retrieves current step from lesson plan
2. Calls Gemini with `TUTOR_EXPLANATION_PROMPT`
3. Generates explanation with analogy/examples
4. Ends with a probing question to check understanding

**Output**: Adds explanation message to state and sets `last_action` to 'explained'

#### C. **Evaluation Node** (`evaluate_response`)

**Purpose**: Assesses user's understanding and decides next action.

**Process**:
1. Analyzes user's response to the question
2. Calls Gemini with `EVALUATOR_PROMPT`
3. Uses `EvaluationSchema` tool for structured decision
4. Returns 'proceed' or 're-explain' action

**Output**: 
- If 'proceed': Increments `lesson_step`
- If 're-explain': Adds feedback message

#### D. **Reflection Node** (`reflect_on_knowledge_gaps`)

**Purpose**: Identifies knowledge gaps for personalized learning.

**Process**:
1. Reviews conversation history
2. Calls Gemini with `REFLECTION_PROMPT`
3. Identifies concepts the user struggled with
4. Updates knowledge gaps list

**Output**: Updates `knowledge_gaps` in state

### 4. Control Flow

The agent uses **conditional routing** to determine the next node:

```
START → plan_lesson → generate_explanation → [User Response] → evaluate_response
                            ↑                                           ↓
                            |                                    (re-explain)
                            └───────────────────────────────────────────┘
                                                                        ↓
                                                                   (proceed)
                                                                        ↓
                                                        [More steps?] → generate_explanation
                                                                        ↓
                                                                   [Complete]
                                                                        ↓
                                                                     reflect → END
```

**Routing Logic** (`should_continue`):
- After planning → Generate first explanation
- After explanation → Wait for user response (end turn)
- After evaluation:
  - If 're-explain' → Generate explanation again
  - If 'proceed' and more steps → Generate next explanation
  - If 'proceed' and all steps done → Reflect on gaps
  - Otherwise → End

### 5. Memory & Persistence

#### Short-Term Memory (MongoDB Checkpointer)

- **Purpose**: Maintains conversation state across API calls
- **Implementation**: `MongoDBSaver` from `langgraph-checkpoint-mongodb`
- **Collection**: `guided_learning_agent_checkpoints`
- **Thread ID**: Uses `session_id` for user-specific threads

```python
checkpointer = MongoDBSaver(
    client=MongoClient(MONGODB_URI),
    collection_name="guided_learning_agent_checkpoints"
)
```

#### Long-Term Memory (Knowledge Gaps)

- **Purpose**: Tracks topics user struggled with across sessions
- **Storage**: Part of agent state, persisted via checkpointer
- **Future Enhancement**: Separate MongoDB collection for cross-session analytics

### 6. Structured Outputs (Pydantic Schemas)

#### `LessonPlanSchema`
```python
class LessonPlanSchema(BaseModel):
    topic: str                # Refined topic name
    steps: list[str]          # List of lesson steps
```

#### `EvaluationSchema`
```python
class EvaluationSchema(BaseModel):
    action: Literal['proceed', 're-explain']  # Next action
    feedback: str                              # Feedback/hint
    understanding_level: int                   # 1-10 rating
```

### 7. Prompts

Each node uses specialized prompts:

- **`LESSON_PLANNER_PROMPT`**: Creates structured lesson plans
- **`TUTOR_EXPLANATION_PROMPT`**: Generates engaging explanations
- **`EVALUATOR_PROMPT`**: Assesses understanding with empathy
- **`REFLECTION_PROMPT`**: Identifies knowledge gaps

All prompts are designed to:
- Be clear and actionable
- Encourage structured outputs
- Maintain a friendly, supportive tone

## Usage

### Running the Agent

```python
from app.agents.core_agent import run_agent

response = run_agent(
    user={"_id": "user123", "name": "Alice"},
    query="Teach me about photosynthesis",
    session_id="session_abc123"
)
```

### API Endpoint

```bash
POST /agent/query
{
    "query": "Teach me about photosynthesis"
}
```

### Conversation Flow Example

1. **User**: "Teach me about photosynthesis"
2. **Agent** (Planning): "I've created a lesson plan for 'Photosynthesis' with 5 steps. Let's begin!"
3. **Agent** (Explanation): "Let's explore what photosynthesis is... [explanation] ... Can you explain why plants need sunlight?"
4. **User**: "Because they use it to make food"
5. **Agent** (Evaluation → Proceed): "Great understanding! Let's move to the next step..."
6. **Agent** (Next Explanation): "Now let's learn about chlorophyll..."

## Optimizations & Enhancements

### Current Optimizations

1. **Fallback Mechanisms**: Each node has error handling with sensible defaults
2. **Logging**: Comprehensive logging for debugging and monitoring
3. **Structured Outputs**: Using Pydantic schemas ensures reliable LLM responses
4. **Conditional Routing**: Efficient flow control based on state

### Future Enhancements

1. **Quiz Mode**: 
   - Implement `quiz_mode` flag functionality
   - Generate assessment questions at lesson end
   - Track performance metrics

2. **Long-Term Knowledge Graph**:
   - Separate MongoDB collection for user knowledge profiles
   - Track mastery levels across topics
   - Recommend related topics based on gaps

3. **Adaptive Difficulty**:
   - Adjust explanation complexity based on user performance
   - Personalize lesson plans to user's grade level

4. **Multi-Modal Support**:
   - Add diagram generation for visual learners
   - Support voice input/output for accessibility

5. **Collaborative Learning**:
   - Group session support
   - Peer comparison (anonymized)

6. **Analytics Dashboard**:
   - Track learning progress over time
   - Identify common knowledge gaps
   - Generate insights for educators

## Configuration

### Environment Variables

```bash
MONGODB_CONNECTION_STRING=mongodb://...
GOOGLE_API_KEY=your_gemini_api_key
```

### MongoDB Collections

- `guided_learning_agent_checkpoints`: Agent state persistence
- `sessions`: User session metadata
- `users`: User profiles and preferences

## Dependencies

Key packages:
```
langgraph==1.0.4
langgraph-checkpoint==3.0.1
langgraph-checkpoint-mongodb==2.0.6
langchain-google-genai==3.0.0
pymongo==4.15.3
pydantic==2.12.3
```

## Testing

### Manual Testing
```bash
# Start the server
uvicorn app.main:app --reload

# Test the endpoint
curl -X POST http://localhost:8000/agent/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"query": "Teach me about the water cycle"}'
```

### Unit Testing (Future)
- Test each node independently
- Mock LLM responses
- Verify state transitions
- Test error handling

## Troubleshooting

### Common Issues

1. **No tool calls in response**
   - Ensure Gemini model supports function calling
   - Check prompt clarity
   - Verify schema definitions

2. **State not persisting**
   - Verify MongoDB connection
   - Check `thread_id` in config
   - Ensure checkpointer is properly initialized

3. **Infinite loops**
   - Review conditional routing logic
   - Check `last_action` state updates
   - Verify `lesson_step` increments

## References

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Gemini API Documentation](https://ai.google.dev/docs)
- [MongoDB Checkpointer](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-mongodb)

---

**Last Updated**: December 2025  
**Version**: 2.0  
**Maintainer**: Development Team
