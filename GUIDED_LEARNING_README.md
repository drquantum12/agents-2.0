# 🎓 Guided Learning Agent - README

## Overview

This is a **state-of-the-art AI-powered Guided Learning Agent** built with:
- **LangGraph** for workflow orchestration
- **Google Gemini API** for intelligent reasoning
- **MongoDB** for state persistence and memory
- **FastAPI** for API endpoints

The agent provides **structured, adaptive learning experiences** by breaking down topics into progressive steps, evaluating understanding, and providing personalized feedback.

## 🌟 Key Features

### ✅ Intelligent Lesson Planning
- Automatically breaks down any topic into 3-5 progressive learning steps
- Creates structured learning paths from foundational to advanced concepts

### ✅ Adaptive Teaching
- Explains concepts using analogies and examples
- Asks probing questions to check understanding
- Provides hints and re-explanations when needed

### ✅ Understanding Evaluation
- Assesses student responses with empathy
- Decides whether to proceed or re-explain
- Rates understanding on a 1-10 scale

### ✅ Knowledge Gap Tracking
- Identifies concepts students struggle with
- Tracks gaps across sessions for personalization
- Enables targeted review and practice

### ✅ Session Persistence
- Maintains conversation state across API calls
- Survives server restarts via MongoDB checkpointing
- Supports multi-turn learning conversations

## 🏗️ Architecture

### Workflow
```
User Query → Plan Lesson → Generate Explanation → User Response → 
Evaluate Response → {Proceed | Re-explain} → ... → Reflect → End
```

### State Management
The agent maintains a comprehensive state with 10 fields:
- User information and query
- Lesson topic and plan
- Current step and progress
- Conversation history
- Knowledge gaps
- Workflow state

### Nodes
1. **plan_lesson**: Creates structured lesson plan
2. **generate_explanation**: Explains concepts + asks questions
3. **evaluate_response**: Assesses understanding
4. **reflect**: Identifies knowledge gaps

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| **IMPLEMENTATION_SUMMARY.md** | Overview of what was implemented |
| **GUIDED_LEARNING_ARCHITECTURE.md** | Detailed architecture documentation |
| **MIGRATION_GUIDE_GUIDED_LEARNING.md** | Migration from old to new architecture |
| **QUICK_REFERENCE.md** | Quick reference with examples |
| **API_REFERENCE.md** | API endpoint documentation |

## 🚀 Quick Start

### Prerequisites
```bash
# Python 3.9+
# MongoDB running locally or remote
# Google Gemini API key
```

### Installation
```bash
# Clone the repository
cd backend

# Create virtual environment
python -m venv env
source env/bin/activate  # On Windows: env\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration
```bash
# Set environment variables
export MONGODB_CONNECTION_STRING="mongodb://localhost:27017/neurosattva"
export GOOGLE_API_KEY="your_gemini_api_key"
```

### Run Tests
```bash
# Structure test (no env vars needed)
python test_agent_structure.py

# Full test (requires env vars)
python test_guided_agent.py
```

### Start Server
```bash
uvicorn app.main:app --reload
```

### Test API
```bash
curl -X POST http://localhost:8000/agent/query \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "Teach me about photosynthesis"}'
```

## 💡 Usage Examples

### Python
```python
from app.agents.core_agent import run_agent

# Start a lesson
response = run_agent(
    user={"_id": "user123", "name": "Alice"},
    query="Teach me about the water cycle",
    session_id="session_001"
)
print(response)
# Output: "I've created a lesson plan for 'The Water Cycle' with 5 steps..."

# Continue the lesson
response = run_agent(
    user={"_id": "user123", "name": "Alice"},
    query="Water evaporates when heated by the sun",
    session_id="session_001"
)
print(response)
# Output: "Excellent! You understand evaporation. Let's move to condensation..."
```

### API
```bash
# First call - creates lesson plan
POST /agent/query
{
    "query": "Teach me about the water cycle"
}

# Response
{
    "response": "I've created a lesson plan for 'The Water Cycle' with 5 steps. Let's begin! The water cycle is Earth's natural recycling system for water..."
}

# Second call - evaluates and continues
POST /agent/query
{
    "query": "Water evaporates when heated"
}

# Response
{
    "response": "Great understanding! Now let's explore what happens when water vapor rises into the atmosphere..."
}
```

## 🔧 Configuration

### Environment Variables
| Variable | Description | Example |
|----------|-------------|---------|
| `MONGODB_CONNECTION_STRING` | MongoDB connection URI | `mongodb://localhost:27017/neurosattva` |
| `GOOGLE_API_KEY` | Google Gemini API key | `AIza...` |

### Constants (in `core_agent.py`)
```python
MAX_STEPS = 5  # Maximum lesson steps (adjust as needed)
```

## 🗄️ Database Collections

### guided_learning_agent_checkpoints
Stores agent state for session persistence
```json
{
    "thread_id": "session_001",
    "checkpoint": {
        "query": "Teach me about photosynthesis",
        "topic": "Photosynthesis in Plants",
        "lesson_step": 2,
        "messages": [...],
        ...
    }
}
```

### sessions
Stores session metadata
```json
{
    "session_id": "device_session_id_user123",
    "created_at": "2025-12-07T09:00:00Z"
}
```

## 🧪 Testing

### Structure Test
Validates code structure without requiring database or API keys:
```bash
python test_agent_structure.py
```

### Full Integration Test
Tests complete agent execution (requires MongoDB and Gemini API):
```bash
python test_guided_agent.py
```

## 🐛 Troubleshooting

### Common Issues

**Issue**: "No module named 'langgraph'"  
**Solution**: Activate virtual environment and install dependencies
```bash
source env/bin/activate
pip install -r requirements.txt
```

**Issue**: "MONGODB_CONNECTION_STRING not set"  
**Solution**: Set environment variable
```bash
export MONGODB_CONNECTION_STRING="mongodb://localhost:27017/neurosattva"
```

**Issue**: "No tool calls in response"  
**Solution**: Ensure using Gemini 1.5 Pro or later (supports function calling)

**Issue**: "State not persisting"  
**Solution**: Check MongoDB connection and verify checkpointer initialization

### Enable Debug Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Agent State
```javascript
// In MongoDB shell
db.guided_learning_agent_checkpoints.find().pretty()
```

## 📊 Monitoring

### Logs
The agent logs at INFO level by default:
```
INFO:app.agents.core_agent:Planning lesson for topic: photosynthesis
INFO:app.agents.core_agent:Generated lesson plan with 5 steps
INFO:app.agents.core_agent:Generating explanation for step 1 of 5
INFO:app.agents.core_agent:Evaluating user response
INFO:app.agents.core_agent:Evaluation result: proceed
```

### MongoDB Queries
```javascript
// Count checkpoints
db.guided_learning_agent_checkpoints.count()

// Find by session
db.guided_learning_agent_checkpoints.find({"thread_id": "session_001"})

// View recent sessions
db.sessions.find().sort({"created_at": -1}).limit(10)
```

## 🚀 Future Enhancements

### Planned Features
- [ ] Quiz mode with formal assessments
- [ ] Multi-session learning paths
- [ ] Adaptive difficulty based on performance
- [ ] Visual aids generation (diagrams, charts)
- [ ] Voice input/output support
- [ ] Collaborative learning sessions
- [ ] Analytics dashboard
- [ ] Spaced repetition for review

### Extension Points
- Custom nodes for specific domains (math, science, etc.)
- Integration with external knowledge bases (RAG)
- Multi-language support
- Gamification elements

## 📖 API Endpoints

### POST /agent/query
Execute the guided learning agent

**Request**:
```json
{
    "query": "Teach me about photosynthesis"
}
```

**Response**:
```json
{
    "response": "I've created a lesson plan for 'Photosynthesis' with 5 steps. Let's begin! ..."
}
```

**Authentication**: Bearer token required

See `API_REFERENCE.md` for complete API documentation.

## 🤝 Contributing

### Code Style
- Follow PEP 8 guidelines
- Add type hints to all functions
- Include docstrings for public functions
- Add logging for important operations

### Testing
- Write tests for new features
- Ensure all tests pass before committing
- Update documentation as needed

## 📄 License

[Your License Here]

## 👥 Team

[Your Team Information]

## 📞 Support

For issues, questions, or contributions:
- Check documentation in `/backend/` directory
- Review `QUICK_REFERENCE.md` for common issues
- Check logs for error messages
- Verify environment variables

---

**Version**: 2.0  
**Last Updated**: December 2025  
**Status**: Production Ready ✅
