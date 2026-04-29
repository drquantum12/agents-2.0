"""
LangGraph Companion Agent v3
Companion + Socratic Mentor with dual-mode learning
Stateful across sessions with MongoDB checkpoint storage and student world model
"""

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from typing import TypedDict, Annotated, Literal
from app.agents.llm import LLM
from langgraph.checkpoint.mongodb import MongoDBSaver
from pymongo import MongoClient
import os
import logging
import operator
import re
import json
from datetime import date, datetime

try:
    from bson import ObjectId
except Exception:  # pragma: no cover
    ObjectId = None

logger = logging.getLogger(__name__)

# Initialize LLM and Vector DB
llm = LLM().get_llm()
fast_llm = llm  # For routing, can use a lighter model if available
vector_db = None  # Lazy-loaded in retrieve_context

def get_vector_db():
    """Lazy-load vector DB on first use."""
    global vector_db
    if vector_db is None:
        from app.db_utility.vector_db import VectorDB
        vector_db = VectorDB()
    return vector_db


def _sanitize_for_checkpoint(value):
    """Convert Mongo/Python objects into msgpack-safe primitives for LangGraph state."""
    if ObjectId is not None and isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _sanitize_for_checkpoint(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_for_checkpoint(v) for v in value]
    return value

# Setup MongoDB connection
mongo_client = MongoClient(os.getenv("MONGODB_CONNECTION_STRING"))
mongo_db = mongo_client["neurosattva"]
student_memory_collection = mongo_db["student_memory"]

# Setup checkpoint saver
checkpointer = MongoDBSaver(
    client=mongo_client,
    db_name="neurosattva",
    ttl=60 * 60 * 24 * 30,  # 30 days
)

# ========================================
# PATTERN MATCHING FOR RULE-BASED ROUTING
# ========================================

YES_PATTERNS = [
    r"^(yes|yeah|yep|yup|sure|ok(?:ay)?|absolutely|definitely|please|go\s+ahead|let'?s?\s+do\s+it|let'?s?\s+go|sounds?\s+good|why\s+not|of\s+course|i'?d?\s+(?:like|love)\s+(?:that|to))[\s!.]*$",
    r"^(break\s+it\s+down|explain\s+(?:it|in\s+detail)|teach\s+me|tell\s+me\s+more|go\s+ahead|i\s+want\s+to\s+learn)",
    r"^haan$",  # Hindi "yes"
]

NO_PATTERNS = [
    r"^(no|nah|nope|not?\s+(?:really|now|thanks)|i'?m?\s+good|skip|never\s*mind|that'?s?\s+(?:enough|fine|okay|ok))[\s!.]*$",
    r"^(i\s+don'?t\s+(?:want|need)|no\s+thanks?|that'?s?\s+all)[\s!.]*$",
    r"^nahi$",  # Hindi "no"
]

STOP_PATTERNS = [
    r"^(stop|exit|enough|band\s+karo|quit|i'?m?\s+done|that'?s?\s+(?:all|enough)|finish)",
    r"^(that\s+was\s+enough|no\s+more|no\s+further)",
]

LEARNING_INTENT_PATTERNS = [
    r"\b(explain|teach|help me (?:learn|understand)|run me through|walk me through|break it down)\b",
    r"\b(tell me (?:about|something about)|what is|how does|how do|why does|why do)\b",
    r"\b(photosynthesis|trigonometry|algebra|chemistry|physics|biology|history|geography)\b",
]


def is_yes(text: str) -> bool:
    """Fast pattern-based yes detection."""
    text_lower = text.strip().lower()
    for pattern in YES_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False


def is_no(text: str) -> bool:
    """Fast pattern-based no detection."""
    text_lower = text.strip().lower()
    for pattern in NO_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False


def is_stop(text: str) -> bool:
    """Fast pattern-based stop detection."""
    text_lower = text.strip().lower()
    for pattern in STOP_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False


def is_learning_intent(text: str) -> bool:
    """Fast pattern-based learning intent detection in general mode."""
    text_lower = text.strip().lower()
    for pattern in LEARNING_INTENT_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False


def extract_topic_from_text(text: str) -> str:
    """Heuristic topic extraction for fast-path routing."""
    cleaned = text.strip().strip("?.! ")
    lowered = cleaned.lower()
    prefixes = [
        "tell me something about ",
        "tell me about ",
        "explain ",
        "teach me ",
        "help me understand ",
        "what is ",
        "how does ",
        "why does ",
    ]
    for prefix in prefixes:
        if lowered.startswith(prefix):
            topic = cleaned[len(prefix):].strip()
            return topic if topic else cleaned
    return cleaned


def _extract_json_object(text: str) -> dict | None:
    """Parse JSON either directly or from a fenced block/substring."""
    if not text:
        return None
    candidate = text.strip()
    try:
        return json.loads(candidate)
    except Exception:
        pass

    # Extract from markdown code fences or mixed text responses.
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = candidate[start:end + 1]
        try:
            return json.loads(snippet)
        except Exception:
            return None
    return None


# ========================================
# AGENT STATE SCHEMA
# ========================================

class AgentState(TypedDict):
    """
    The unified state for the companion+mentor agent.
    Everything flows through this state and persists via MongoDB checkpointer.
    """
    # --- Core conversation ---
    messages: Annotated[list[BaseMessage], operator.add]
    
    # --- Routing (set by intent_router each turn) ---
    route: str  # "general" | "teacher" | "stop_teacher"
    sub_intent: str  # teacher mode only: "new_topic", "continue", "step_complete", "digress", "digress_resume", "digress_exit"
    
    # --- Mode tracking (persists across turns) ---
    mode: str  # "general" | "teacher"
    
    # --- Teacher mode state ---
    active_topic: str | None  # the lesson topic
    lesson_plan: list[str]  # 3-5 step descriptions
    current_step: int  # 0-indexed
    step_context: list[dict]  # context chunks from Milvus for current step
    pending_resume: bool  # waiting for yes/no after digression
    awaiting_lesson_confirmation: bool  # waiting for yes/no after lesson offer in general mode
    pending_topic: str | None  # proposed topic while waiting for lesson confirmation
    
    # --- Long-term memory (loaded at session start) ---
    student_profile: dict  # world model: mastered_concepts, struggling_concepts, personality, etc.
    world_model_dirty: bool  # True if profile needs saving
    
    # --- Session metadata ---
    user_id: str


# ========================================
# STUDENT PROFILE MANAGEMENT
# ========================================

def load_student_profile(user_id: str) -> dict:
    """Load or create student's long-term world model."""
    try:
        profile = student_memory_collection.find_one({"user_id": user_id})
        if not profile:
            # Create default profile
            profile = {
                "user_id": user_id,
                "name": user_id.split("_")[0] if "_" in user_id else user_id,
                "grade": 10,
                "board": "CBSE",
                "subject": "Mathematics",
                "learning_style": "example-driven",
                "personality_notes": "",
                "interests": [],
                "mastered_concepts": [],
                "struggling_concepts": [],
                "session_summaries": [],
                "total_sessions": 0,
                "last_active": None,
            }
            student_memory_collection.insert_one(profile)
            logger.info(f"Created new student profile for {user_id}")
        # Never keep Mongo's internal _id in graph state.
        profile.pop("_id", None)
        return _sanitize_for_checkpoint(profile)
    except Exception as e:
        logger.error(f"Error loading student profile: {e}")
        # Return minimal default profile
        return {
            "user_id": user_id,
            "name": user_id,
            "grade": 10,
            "board": "CBSE",
            "learning_style": "example-driven",
            "interests": [],
            "mastered_concepts": [],
            "struggling_concepts": [],
        }


def save_student_profile(user_id: str, profile: dict):
    """Save updated student world model to MongoDB."""
    try:
        profile_to_save = _sanitize_for_checkpoint(profile)
        profile_to_save.pop("_id", None)
        profile_to_save["user_id"] = str(user_id)
        student_memory_collection.replace_one(
            {"user_id": user_id},
            profile_to_save,
            upsert=True
        )
        logger.info(f"Saved student profile for {user_id}")
    except Exception as e:
        logger.error(f"Error saving student profile: {e}")


# ========================================
# NODES
# ========================================

def intent_router(state: AgentState) -> dict:
    """
    Entry node that runs every turn. Classifies student's intent.
    Uses rule-based fast path first, LLM fallback for ambiguous cases.
    Sets route and sub_intent for downstream nodes.
    """
    messages = state.get("messages", [])
    if not messages:
        return {"route": "general", "sub_intent": ""}
    
    last_message = messages[-1]
    if not isinstance(last_message, HumanMessage):
        return {"route": "general", "sub_intent": ""}
    
    user_input = last_message.content
    mode = state.get("mode", "general")
    active_topic = state.get("active_topic")
    active_topic_text = (active_topic or "").strip()
    pending_resume = state.get("pending_resume", False)
    awaiting_lesson_confirmation = state.get("awaiting_lesson_confirmation", False)
    pending_topic = state.get("pending_topic")
    
    logger.info(f"Routing: mode={mode}, pending_resume={pending_resume}, input='{user_input[:50]}'")
    
    # --- FAST PATH: Resume handling ---
    if mode == "teacher" and pending_resume:
        if is_yes(user_input):
            logger.info("User confirmed resuming lesson")
            return {"route": "teacher", "sub_intent": "digress_resume", "pending_resume": False}
        elif is_no(user_input):
            logger.info("User declined resuming lesson")
            return {"route": "stop_teacher", "sub_intent": "digress_exit", "pending_resume": False}

    # --- FAST PATH: General-mode lesson confirmation ---
    if mode == "general" and awaiting_lesson_confirmation:
        if is_yes(user_input):
            chosen_topic = pending_topic or active_topic or "this topic"
            logger.info(f"User confirmed lesson start for topic: {chosen_topic}")
            return {
                "route": "teacher",
                "sub_intent": "new_topic",
                "active_topic": chosen_topic,
                "awaiting_lesson_confirmation": False,
            }
        if is_no(user_input):
            logger.info("User declined lesson offer")
            return {
                "route": "general",
                "sub_intent": "",
                "awaiting_lesson_confirmation": False,
                "pending_topic": None,
            }

    # --- FAST PATH: General-mode implicit confirmation ---
    # If the previous assistant turn offered a lesson and user says yes, start teacher mode.
    if mode == "general" and is_yes(user_input):
        previous_ai_messages = [m for m in messages[:-1] if isinstance(m, AIMessage)]
        last_ai_content = previous_ai_messages[-1].content.lower() if previous_ai_messages else ""
        offered_lesson_markers = [
            "want me to run you through",
            "want me to break",
            "step by step",
            "detailed lesson",
        ]
        if any(marker in last_ai_content for marker in offered_lesson_markers):
            inferred_topic = pending_topic or active_topic_text or "this topic"
            logger.info(f"Implicit confirmation detected, starting teacher mode for: {inferred_topic}")
            return {
                "route": "teacher",
                "sub_intent": "new_topic",
                "active_topic": inferred_topic,
                "awaiting_lesson_confirmation": False,
                "pending_topic": None,
            }
    
    # --- FAST PATH: Stop detection ---
    if is_stop(user_input):
        logger.info("User wants to stop lesson")
        return {"route": "stop_teacher", "sub_intent": ""}

    # --- FAST PATH: Learning intent in general mode ---
    if mode == "general" and is_learning_intent(user_input):
        topic = extract_topic_from_text(user_input)
        logger.info(f"Learning intent fast-path detected, topic={topic}")
        return {
            "route": "teacher",
            "sub_intent": "new_topic",
            "active_topic": topic,
            "awaiting_lesson_confirmation": False,
            "pending_topic": None,
        }
    
    # --- LLM CLASSIFIER (for everything else) ---
    classifier_prompt = f"""
You are a classifier for student learning intents.

Current mode: {mode}
Student message: "{user_input}"
Active lesson topic: "{active_topic}"

Classify this as exactly ONE of:
- general_chat: casual talk, not studying-related
- learning_intent: wants to learn/understand a new topic
- lesson_continue: responding within active lesson (answering question, asking on-topic clarification)
- lesson_digress: off-topic question during active lesson
- lesson_stop: wants to end current lesson

Return ONLY valid JSON: {{"intent": "<one of above>", "topic": "<if learning_intent, what topic; else empty>"}}
"""
    
    try:
        response = fast_llm.invoke(classifier_prompt)
        result = _extract_json_object(response.content)
        if not result:
            raise ValueError("Classifier did not return valid JSON object")
        intent = result.get("intent", "general_chat")
        topic = result.get("topic", user_input)
        
        logger.info(f"Classifier intent: {intent}")
        
        # Map classifier output to route + sub_intent
        if intent == "general_chat":
            return {"route": "general", "sub_intent": ""}
        
        elif intent == "learning_intent":
            if mode == "teacher" and topic.lower() == active_topic_text.lower():
                return {"route": "teacher", "sub_intent": "continue"}
            else:
                return {"route": "teacher", "sub_intent": "new_topic", "active_topic": topic}
        
        elif intent == "lesson_continue":
            return {"route": "teacher", "sub_intent": "continue"}
        
        elif intent == "lesson_digress":
            return {"route": "teacher", "sub_intent": "digress"}
        
        elif intent == "lesson_stop":
            return {"route": "stop_teacher", "sub_intent": ""}
        
    except Exception as e:
        logger.warning(f"Classifier LLM error: {e}, applying rule fallback")
        if mode == "general" and is_learning_intent(user_input):
            topic = extract_topic_from_text(user_input)
            return {
                "route": "teacher",
                "sub_intent": "new_topic",
                "active_topic": topic,
                "awaiting_lesson_confirmation": False,
                "pending_topic": None,
            }
    
    return {"route": "general", "sub_intent": ""}


def retrieve_context(state: AgentState) -> dict:
    """
    Retrieves concept chunks from Milvus for the current lesson step.
    Only runs when new_topic or step_complete is detected.
    """
    sub_intent = state.get("sub_intent", "")
    active_topic = state.get("active_topic", "")
    lesson_plan = state.get("lesson_plan", [])
    current_step = state.get("current_step", 0)
    student_profile = state.get("student_profile", {})
    
    if sub_intent == "new_topic":
        query_text = active_topic
    else:  # step_complete or continue with context refresh
        if current_step < len(lesson_plan):
            query_text = lesson_plan[current_step]
        else:
            query_text = active_topic
    
    logger.info(f"Retrieving context for: {query_text}")
    
    try:
        # Get vector DB instance (lazy-loaded)
        vdb = get_vector_db()
        
        # Query Milvus with curriculum filters
        board = student_profile.get("board", "CBSE")
        grade = student_profile.get("grade", 10)
        
        content, sources = vdb.get_similar_documents(
            text=query_text,
            top_k=3,
            board=board,
            grade=grade
        )
        
        # Parse returned content into structured chunks
        # (Assuming vector_db returns formatted content; adjust parsing as needed)
        step_context = [
            {
                "concept": query_text,
                "explanation": content,
                "analogies": "",
                "chapter": "",
                "subject": student_profile.get("subject", "Mathematics"),
                "doc_id": sources[0] if sources else "",
            }
        ]
        
        logger.info(f"Retrieved {len(step_context)} context chunks")
        return {"step_context": step_context}
        
    except Exception as e:
        logger.error(f"Error retrieving context: {e}")
        return {"step_context": []}


def general_node(state: AgentState) -> dict:
    """
    Generates friendly companion response in general mode.
    Knows the student well (interests, mastered concepts, personality).
    """
    messages = state.get("messages", [])
    student_profile = state.get("student_profile", {})
    route = state.get("route", "")
    
    logger.info(f"Generating general mode response (route={route})")
    
    # If transitioning from teacher mode (stop_teacher), add farewell note
    farewell_note = ""
    reset_state = {}
    if route == "stop_teacher" and state.get("mode") == "teacher":
        active_topic = state.get("active_topic", "")
        current_step = state.get("current_step", 0)
        lesson_plan = state.get("lesson_plan", [])
        farewell_note = f"(Note: student ended lesson on '{active_topic}' at step {current_step + 1} of {len(lesson_plan)})"
        reset_state = {
            "mode": "general",
            "active_topic": None,
            "lesson_plan": [],
            "current_step": 0,
            "step_context": [],
            "pending_resume": False,
        }

    # In general mode, explicitly close lesson-offer flow on decline.
    if state.get("awaiting_lesson_confirmation") and is_no(messages[-1].content if messages else ""):
        reset_state.update({
            "awaiting_lesson_confirmation": False,
            "pending_topic": None,
        })
    
    # Build rich system prompt
    recent_sessions = student_profile.get("session_summaries", [])[-3:]
    recent_mastered = student_profile.get("mastered_concepts", [])[-5:]
    
    system_prompt = f"""
You are {student_profile.get('name', 'my friend')}'s personal companion — a self-aware, warm, slightly witty friend
who happens to know a lot about everything.

About your friend:
- Name: {student_profile.get('name', 'them')}
- Grade: {student_profile.get('grade', 10)}, Board: {student_profile.get('board', 'CBSE')}
- Interests: {', '.join(student_profile.get('interests', []))}
- Personality: {student_profile.get('personality_notes', 'friendly and curious')}

What they've learned with you:
{chr(10).join([c.get('concept', '') for c in recent_mastered]) if recent_mastered else 'Just getting started!'}

{farewell_note}

TONE RULES:
- Talk like a real friend. Short, natural sentences.
- Reference their interests casually if relevant.
- No "As an AI" or "I'm here to help" clichés. Just talk.
- If they mention a topic they want to learn, gently ask "want me to run you through it?" — but only once.
- No bullet points. Just plain conversation.
"""
    
    try:
        response = llm.invoke([SystemMessage(content=system_prompt)] + messages)
        return {
            "messages": [AIMessage(content=response.content)],
            **reset_state
        }
    except Exception as e:
        logger.error(f"Error in general_node: {e}")
        return {
            "messages": [AIMessage(content="I'm here to chat! What's on your mind?")],
            **reset_state
        }


def teacher_node(state: AgentState) -> dict:
    """
    Generates Socratic mentor responses in teacher mode.
    Handles all teaching sub_intents: new_topic, continue, digress, digress_resume, digress_exit.
    """
    sub_intent = state.get("sub_intent", "")
    student_profile = state.get("student_profile", {})
    active_topic = state.get("active_topic", "")
    lesson_plan = state.get("lesson_plan", [])
    current_step = state.get("current_step", 0)
    step_context = state.get("step_context", [])
    messages = state.get("messages", [])
    
    logger.info(f"Teacher node: sub_intent={sub_intent}, step={current_step}/{len(lesson_plan)}")
    
    # --- BRANCH: new_topic ---
    if sub_intent == "new_topic":
        return _handle_new_topic(state, student_profile, active_topic, step_context, messages)
    
    # --- BRANCH: continue ---
    elif sub_intent == "continue":
        return _handle_continue(state, student_profile, active_topic, lesson_plan, current_step, step_context, messages)
    
    # --- BRANCH: digress ---
    elif sub_intent == "digress":
        return _handle_digress(state, active_topic, current_step, lesson_plan, messages)
    
    # --- BRANCH: digress_resume ---
    elif sub_intent == "digress_resume":
        return _handle_digress_resume(state, active_topic, current_step, lesson_plan, messages)
    
    # --- BRANCH: digress_exit ---
    elif sub_intent == "digress_exit":
        return _handle_digress_exit(state)
    
    return {"messages": [AIMessage(content="Let me help you with your lesson.")]}


def _handle_new_topic(state: AgentState, student_profile: dict, active_topic: str, step_context: list, messages: list) -> dict:
    """Generate lesson plan AND teach step 1 in a single LLM call."""
    logger.info(f"New topic: {active_topic}")
    
    context_text = chr(10).join([c.get('explanation', '') for c in step_context]) if step_context else ''
    interests = ', '.join(student_profile.get('interests', []))
    grade = student_profile.get('grade', 10)
    name = student_profile.get('name', 'the student')
    
    # Single combined call: plan + teach step 1 together
    combined_prompt = f"""
You are {name}'s personal mentor. The student wants to learn: "{active_topic}"

You have two tasks. Do BOTH in one response.

TASK 1 — Build a 3-5 step lesson plan for CBSE grade {grade} (basics to advanced).
TASK 2 — Teach step 1 right now: explain clearly, use an analogy from their interests, end with ONE Socratic question. 3-5 sentences, conversational tone.

CONCEPT CONTEXT (use as ground truth):
{context_text if context_text else 'Teach from general knowledge.'}

STUDENT INTERESTS (for analogies): {interests if interests else 'general topics'}

Respond in EXACTLY this format — no extra text:
LESSON_PLAN: ["step 1 desc", "step 2 desc", "step 3 desc"]
---
[Your teaching for step 1 here]
"""
    
    fallback_plan = [
        f"Introduction to {active_topic}",
        f"Core concepts of {active_topic}",
        f"Applications of {active_topic}",
    ]
    
    try:
        response = llm.invoke(combined_prompt)
        raw = response.content.strip()
        
        # Parse LESSON_PLAN line
        lesson_plan = fallback_plan
        teaching_content = raw
        
        if "LESSON_PLAN:" in raw and "---" in raw:
            plan_part, _, teaching_content = raw.partition("---")
            plan_line = plan_part.strip()
            if "LESSON_PLAN:" in plan_line:
                json_str = plan_line.split("LESSON_PLAN:", 1)[1].strip()
                parsed = _extract_json_object(json_str) if not json_str.startswith('[') else None
                try:
                    lesson_plan = json.loads(json_str) if json_str.startswith('[') else (parsed or fallback_plan)
                    if not isinstance(lesson_plan, list) or len(lesson_plan) < 2:
                        lesson_plan = fallback_plan
                    lesson_plan = lesson_plan[:5]
                except Exception:
                    lesson_plan = fallback_plan
        
        teaching_content = teaching_content.strip()
        if "STEP_VERDICT:" in teaching_content:
            teaching_content = teaching_content.rsplit("STEP_VERDICT:", 1)[0].strip()
        
        return {
            "messages": [AIMessage(content=teaching_content)],
            "mode": "teacher",
            "lesson_plan": lesson_plan,
            "current_step": 0,
            "awaiting_lesson_confirmation": False,
            "pending_topic": None,
        }
    except Exception as e:
        logger.error(f"Error in new_topic: {e}")
        return {
            "messages": [AIMessage(content=f"Let's explore {active_topic} together! What do you already know about it?")],
            "mode": "teacher",
            "lesson_plan": fallback_plan,
            "current_step": 0,
            "awaiting_lesson_confirmation": False,
            "pending_topic": None,
        }


def _handle_continue(state: AgentState, student_profile: dict, active_topic: str, 
                     lesson_plan: list, current_step: int, step_context: list, messages: list) -> dict:
    """Assess understanding and respond; advance step if understood. Single LLM call."""
    logger.info(f"Continue lesson: step {current_step + 1}/{len(lesson_plan)}")
    
    is_last_step = (current_step == len(lesson_plan) - 1)
    
    teach_prompt = f"""
You are {student_profile.get('name', 'the student')}'s personal mentor. You're mid-lesson on "{active_topic}".

LESSON PLAN:
{chr(10).join([f"{i+1}. {step}" for i, step in enumerate(lesson_plan)])}

CURRENT STEP ({current_step + 1} of {len(lesson_plan)}) — IS LAST STEP: {is_last_step}:
{lesson_plan[current_step]}

CONCEPT CONTEXT:
{chr(10).join([c.get('explanation', '') for c in step_context]) if step_context else 'Proceed with teaching'}

STUDENT INTERESTS: {', '.join(student_profile.get('interests', []))}

The student's last message was their response to your question.

YOUR TASK:
1. Assess if they understood (understood | partial | not_understood).
2. If UNDERSTOOD and NOT last step: praise naturally, bridge to next step, end with ONE Socratic question.
3. If UNDERSTOOD and IS LAST STEP: congratulate warmly (not over the top), recap lesson in 2-3 sentences, ask if they want a recall exercise.
4. If PARTIAL/NOT_UNDERSTOOD: re-explain with a different analogy, ask simpler question.

Keep it conversational, 3-5 sentences.

At the very end, output:
STEP_VERDICT: understood | partial | not_understood
"""
    
    try:
        response = llm.invoke(teach_prompt)
        raw_content = response.content
        
        verdict = "understood"
        if "STEP_VERDICT:" in raw_content:
            content_part, verdict_part = raw_content.rsplit("STEP_VERDICT:", 1)
            verdict = verdict_part.strip().split()[0].lower()
        else:
            content_part = raw_content
        
        new_step = current_step
        new_mode = "teacher"
        world_model_dirty = False
        
        if verdict == "understood":
            new_step = current_step + 1
            if new_step >= len(lesson_plan):
                new_mode = "general"
                new_step = 0
                world_model_dirty = True
        
        return {
            "messages": [AIMessage(content=content_part.strip())],
            "current_step": new_step,
            "mode": new_mode,
            "world_model_dirty": world_model_dirty,
        }
    except Exception as e:
        logger.error(f"Error in continue: {e}")
        return {
            "messages": [AIMessage(content="Let me know your thoughts on that!")],
        }


def _handle_digress(state: AgentState, active_topic: str, current_step: int, 
                    lesson_plan: list, messages: list) -> dict:
    """Answer off-topic question, then ask to resume."""
    logger.info("Handling digression")
    
    digress_prompt = f"""
You are a mentor. You're in the middle of a lesson on "{active_topic}" (step {current_step + 1} of {len(lesson_plan)}).
The student just asked something unrelated.

Answer briefly (2-4 sentences), as a knowledgeable friend would.

Then, on a new paragraph, gently ask: "Want to get back to {active_topic}?"
Keep it light — no pressure.
"""
    
    try:
        response = llm.invoke(digress_prompt)
        return {
            "messages": [AIMessage(content=response.content)],
            "pending_resume": True,
        }
    except Exception as e:
        logger.error(f"Error in digress: {e}")
        return {
            "messages": [AIMessage(content=f"Got it! Want to get back to {active_topic}?")],
            "pending_resume": True,
        }


def _handle_digress_resume(state: AgentState, active_topic: str, current_step: int, 
                           lesson_plan: list, messages: list) -> dict:
    """Student confirmed resuming; bring them back to lesson."""
    logger.info("Resuming lesson after digression")
    
    resume_prompt = f"""
Student confirmed they want to continue the lesson on "{active_topic}".
We were on step {current_step + 1}: "{lesson_plan[current_step]}"

Warmly bring them back — remind them briefly where they were (one sentence),
then re-ask your last Socratic question. Don't restart.
"""
    
    try:
        response = llm.invoke(resume_prompt)
        return {
            "messages": [AIMessage(content=response.content)],
            "pending_resume": False,
        }
    except Exception as e:
        logger.error(f"Error in digress_resume: {e}")
        return {
            "messages": [AIMessage(content="Great, let's continue!")],
            "pending_resume": False,
        }


def _handle_digress_exit(state: AgentState) -> dict:
    """Student declined resuming; exit lesson gracefully."""
    logger.info("Student exited lesson after digression")
    
    active_topic = state.get("active_topic", "the topic")
    lesson_plan = state.get("lesson_plan", [])
    current_step = state.get("current_step", 0)
    
    msg = f"No problem! We covered {current_step + 1} of {len(lesson_plan)} steps on {active_topic}. Feel free to ask me anything else!"
    
    return {
        "messages": [AIMessage(content=msg)],
        "mode": "general",
        "active_topic": None,
        "lesson_plan": [],
        "current_step": 0,
        "step_context": [],
        "pending_resume": False,
        "awaiting_lesson_confirmation": False,
        "pending_topic": None,
    }


# ========================================
# CONDITIONAL ROUTING
# ========================================

def route_start(state: AgentState) -> str:
    """Entry router: decide first node based on state."""
    route = state.get("route", "general")
    sub_intent = state.get("sub_intent", "")
    
    # If routing says retrieve_context is needed
    if sub_intent in ["new_topic", "step_complete"]:
        return "retrieve_context"
    
    # General or teacher routing
    if route == "general" or route == "stop_teacher":
        return "general_node"
    elif route == "teacher":
        return "teacher_node"
    
    return "general_node"


def route_after_retrieve(state: AgentState) -> str:
    """After retrieve_context, go to teacher_node."""
    return "teacher_node"


# ========================================
# GRAPH CONSTRUCTION
# ========================================

def build_agent():
    """Build and compile the new LangGraph agent."""
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("intent_router", intent_router)
    workflow.add_node("retrieve_context", retrieve_context)
    workflow.add_node("general_node", general_node)
    workflow.add_node("teacher_node", teacher_node)
    
    # Edges
    # Always start with intent classification.
    workflow.add_edge(START, "intent_router")
    
    workflow.add_conditional_edges(
        "intent_router",
        lambda s: "retrieve_context" if s.get("sub_intent") in ["new_topic", "step_complete"] else (
            "general_node" if s.get("route") == "general" or s.get("route") == "stop_teacher" else "teacher_node"
        ),
        {
            "retrieve_context": "retrieve_context",
            "general_node": "general_node",
            "teacher_node": "teacher_node",
        }
    )
    
    workflow.add_edge("retrieve_context", "teacher_node")
    workflow.add_edge("general_node", END)
    workflow.add_edge("teacher_node", END)
    
    # Compile with checkpointer
    app = workflow.compile(checkpointer=checkpointer)
    logger.info("Agent v3 workflow compiled successfully")
    
    return app


# ========================================
# AGENT SINGLETON & RUN FUNCTION
# ========================================

_cached_agent = None


def get_agent():
    """Get or create the agent singleton."""
    global _cached_agent
    if _cached_agent is None:
        _cached_agent = build_agent()
        logger.info("Agent graph built and cached")
    return _cached_agent


def run_agent(user: dict, query: str, session_id: str) -> str:
    """
    Run the companion+mentor agent with full state persistence.
    
    Args:
        user: User dict with '_id' field
        query: User's query/message
        session_id: Session ID for checkpointer
    """
    try:
        user_id = str(user.get("_id", user.get("id", "unknown_user")))
        
        query_text = (query or "").strip()
        if not query_text:
            query_text = "hi"
        logger.info(f"Running agent v3 for user {user_id}: {query[:60]}...")
        
        # Load student profile
        student_profile = load_student_profile(user_id)
        
        # Prepare config for MongoDB checkpointer (thread_id = session_id)
        config = {"configurable": {"thread_id": session_id}}
        
        agent = get_agent()
        
        # Initialize input state
        input_state = {
            "messages": [HumanMessage(content=query_text)],
            "user_id": user_id,
            "student_profile": _sanitize_for_checkpoint(student_profile),
            "route": "",
            "sub_intent": "",
            "mode": "general",
            "active_topic": None,
            "lesson_plan": [],
            "current_step": 0,
            "step_context": [],
            "pending_resume": False,
            "awaiting_lesson_confirmation": False,
            "pending_topic": None,
            "world_model_dirty": False,
        }
        
        # Run agent
        result_state = agent.invoke(input_state, config=config)
        
        # Save profile if dirty
        if result_state.get("world_model_dirty"):
            save_student_profile(
                user_id,
                _sanitize_for_checkpoint(result_state.get("student_profile", student_profile)),
            )
        
        # Extract response
        ai_messages = [m for m in result_state.get("messages", []) if isinstance(m, AIMessage)]
        response = ai_messages[-1].content if ai_messages else "I'm here to help!"
        
        # Clean any STEP_VERDICT tags
        if "STEP_VERDICT:" in response:
            response = response.rsplit("STEP_VERDICT:", 1)[0].strip()
        
        logger.info("Agent invocation completed successfully")
        return response
        
    except Exception as e:
        logger.error(f"Error running agent v3: {e}", exc_info=True)
        raise
