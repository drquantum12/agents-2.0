from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from typing import TypedDict, Annotated, Optional
from app.agents.llm import LLM
from langgraph.checkpoint.mongodb import MongoDBSaver
from pymongo import MongoClient
import os
import logging
import operator
import re
import random
import threading

from app.agents.memory.short_term_memory import get_mongo_saver
from app.agents.memory.long_term_memory import (
    get_student_memory,
    build_memory_summary,
    upsert_student_memory,
    apply_memory_delta,
    filter_and_enrich_delta,
)
from app.db_utility.mongo_db import mongo_db
from app.db_utility.vector_db import VectorDB
from app.agents.prompts import (
    # v1 prompts
    TUTOR_PERSONA,
    ROUTING_PROMPT,
    LESSON_CONTEXT_PROMPT,
    BRIEF_OFFER_PROMPT,
    SMALL_TALK_PROMPT,
    SMALL_TALK_MID_LESSON_PROMPT,
    LESSON_RESUME_PROMPT,
    QA_PROMPT,
    LESSON_PLAN_PROMPT_V2,
    LESSON_INTRO_PROMPT,
    EXPLAIN_PROMPT,
    EVAL_PROMPT_V2,
    FEEDBACK_BRIDGE_PROMPT,
    LESSON_EXIT_PROMPT,
    COMPOSER_PROMPT,
)
from app.agents.schemas import (
    RoutingSchema,
    LessonContextSchema,
    LessonPlanSchema,
    EvaluationSchema,
)

logger = logging.getLogger(__name__)

llm = LLM().get_llm()
llm_with_routing_tool = llm.bind_tools(tools=[RoutingSchema])
llm_with_lesson_context_tool = llm.bind_tools(tools=[LessonContextSchema])
llm_with_lesson_plan_tool = llm.bind_tools(tools=[LessonPlanSchema])
llm_with_eval_tool = llm.bind_tools(tools=[EvaluationSchema])

vector_db = VectorDB()

MAX_STEPS = 5

# ========================================
# FAST-PATH PATTERNS (zero LLM cost)
# ========================================

SMALL_TALK_PATTERNS = [
    r'^(hi|hello|hey|howdy|sup|yo)\b',
    r'^(good\s+)?(morning|afternoon|evening|night)',
    r"how\s+are\s+you",
    r"how'?s?\s+it\s+going",
    r"what'?s?\s+up",
    r"tell\s+me\s+a\s+joke",
    r'^(bye|goodbye|see\s+you|later|take\s+care)',
    r'^(thanks|thank\s+you)',
    r"^i'?m\s+(bored|tired|happy|sad|excited|good|fine|great|ok(?:ay)?)",
    r'^(haha|lol|lmao)',
    r'^who\s+are\s+you',
    r"^what('?s|\s+is)\s+your\s+name",
    r'^(nice|cool|awesome|great|wow)$',
    r"^you'?re?\s+(funny|cool|nice|great|awesome)",
]

REPEAT_REQUEST_PATTERNS = [
    r"(couldn'?t|can'?t|could\s+not|did\s+not|didn'?t)\s+(hear|understand|catch|get)",
    r"(repeat|say\s+(that|it|this)\s+again)",
    r"(come\s+again|pardon|once\s+more|one\s+more\s+time)",
    r"what\s+(did|was)\s+you\s+(say|ask)",
    r"(say|tell|ask)\s+(that|it|me)\s+again",
    r"(again\s+please|please\s+again|please\s+repeat)",
    r"^again$",
    r"(can|could)\s+you\s+(repeat|say\s+(that|it)\s+again)",
    r"i\s+missed\s+(that|it|what\s+you\s+said)",
    r"what\s+(question|did\s+you\s+ask)",
    r"(speak|talk)\s+(louder|up)",
]

META_QUERY_PATTERNS = [
    r"what\s+topics?\s+(have\s+we|did\s+we|we\s+have|we'?ve)\s+",
    r"what\s+have\s+(we|i)\s+been\s+(studying|learning|doing|covering)",
    r"what\s+(have\s+(we|i)|did\s+(we|i))\s+(study|learn|cover|done)",
    r"(show|tell)\s+me\s+(my|our)\s+(progress|history|topics|lessons)",
    r"(my|our)\s+(study|learning)\s+history",
    r"what\s+are\s+we\s+(studying|learning|working\s+on)",
    r"what\s+have\s+i\s+(learned|studied|covered)",
    r"topics?\s+(we'?ve|i'?ve|we\s+have|i\s+have)\s+(covered|studied|done|learned)",
    r"what\s+subjects?\s+(have\s+we|did\s+we|we'?ve)\s+",
    r"(our|my)\s+(lessons?|topics?)\s+so\s+far",
]


def is_small_talk(query: str) -> bool:
    query_lower = query.strip().lower()
    if len(query_lower.split()) <= 10:
        for pattern in SMALL_TALK_PATTERNS:
            if re.search(pattern, query_lower):
                return True
    return False


def is_repeat_request(query: str) -> bool:
    query_lower = query.strip().lower()
    if len(query_lower.split()) <= 15:
        for pattern in REPEAT_REQUEST_PATTERNS:
            if re.search(pattern, query_lower):
                return True
    return False


def is_meta_query(query: str) -> bool:
    query_lower = query.strip().lower()
    for pattern in META_QUERY_PATTERNS:
        if re.search(pattern, query_lower):
            return True
    return False


YES_PATTERNS = [
    r"^(yes|yeah|yep|yup|sure|ok(?:ay)?|absolutely|definitely|please|go\s+ahead)[\s!.]*$",
    r"^(let'?s?\s+(?:do\s+it|go)|sounds?\s+good|why\s+not|of\s+course)[\s!.]*$",
    r"^(i'?d?\s+(?:like|love)\s+(?:that|to)|break\s+it\s+down|explain\s+(?:it|more|in\s+detail))[\s!.]*$",
    r"^(teach\s+me|tell\s+me\s+more|i\s+want\s+to\s+learn|go\s+ahead|please\s+do)[\s!.]*$",
    r"^(right|alright|continue|carry\s+on|go\s+on|let'?s?\s+continue|sounds?\s+right|fine\s+by\s+me)[\s!.]*$",
]

NO_PATTERNS = [
    r"^(no|nah|nope|not?\s+(?:really|now|thanks)|i'?m?\s+good|skip|never\s*mind)[\s!.]*$",
    r"^(that'?s?\s+(?:enough|fine|okay|ok)|no\s+thanks?|that'?s?\s+all)[\s!.]*$",
    r"^(i\s+don'?t\s+(?:want|need)|not\s+interested|maybe\s+later)[\s!.]*$",
]


def is_yes(query: str) -> bool:
    q = query.strip().lower()
    return any(re.search(p, q) for p in YES_PATTERNS)


def is_no(query: str) -> bool:
    q = query.strip().lower()
    return any(re.search(p, q) for p in NO_PATTERNS)


def _strip_tts_symbols(text: str) -> str:
    """Remove characters that sound bad when spoken via TTS."""
    text = re.sub(r'[*#\[\]()\\]', '', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()


def _format_recent_messages(messages: list, n: int = 6) -> str:
    """Return the last n messages as Student/Tutor lines for prompt injection."""
    if not messages:
        return "No prior messages this session."
    recent = messages[-n:]
    lines = []
    for msg in recent:
        if isinstance(msg, HumanMessage):
            lines.append(f"Student: {msg.content}")
        elif isinstance(msg, AIMessage):
            lines.append(f"Tutor: {msg.content}")
    return "\n".join(lines) if lines else "No prior messages this session."


# ========================================
# AGENT STATE (v1 — backward compatible)
# ========================================

class AgentState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────
    query:           str
    user:            dict
    messages:        Annotated[list[BaseMessage], operator.add]
    session_id:      str

    # ── Device config (loaded fresh each turn by context_loader) ───
    difficulty_level: str   # "Beginner" | "Intermediate" | "Advanced"
    response_type:    str   # "Concise" | "Detailed"
    learning_mode:    str   # "Normal" | "Strict"

    # ── Student memory (loaded from MongoDB each turn) ─────────────
    student_memory:  dict
    memory_summary:  str   # ≤4 sentence digest for prompt injection

    # ── RAG ────────────────────────────────────────────────────────
    retrieved_chunks: str  # top-k Milvus results, formatted as plain text

    # ── Routing (set by smart_router) ──────────────────────────────
    intent:          str           # "small_talk"|"qa"|"teach"|"evaluate"
    topic_slug:      Optional[str]
    topic_name:      Optional[str]
    diagnosis:       Optional[str]
    is_exiting_lesson: bool
    repeat_requested:  bool

    # ── Lesson state (mirrored from student_memory by context_loader)
    current_topic:       Optional[str]
    lesson_subtopics:    list
    lesson_step:         int

    # ── Memory delta (accumulated during turn, written by composer) ─
    memory_delta:    dict

    # ── Output ─────────────────────────────────────────────────────
    agent_output:    str   # raw content from responder
    last_response:   str   # final TTS-safe content from composer
    last_explanation: str  # stored for repeat requests
    skip_composer:   bool  # skip LLM call in composer (used for repeats)

    # ── Backward-compat fields (kept so old checkpoints don't break) ─
    mode:                       str
    topic:                      str
    lesson_plan:                list
    lesson_step_legacy:         int
    last_action:                str
    awaiting_lesson_confirmation: bool
    pending_topic:              str
    feedback:                   str


# ========================================
# SETUP CHECKPOINTER
# ========================================

checkpointer = get_mongo_saver()


# ========================================
# NODE 1: context_loader (no LLM)
# ========================================

def context_loader(state: AgentState) -> dict:
    """
    Loads device config, student memory, and Milvus RAG content.
    No LLM calls. Runs first every turn.
    """
    user = state.get("user", {})
    user_id = str(user.get("_id", ""))

    # 1. Device config
    config = mongo_db["device_config"].find_one({"user_id": user_id}) or {}
    difficulty_level = config.get("difficulty_level", "Beginner")
    response_type    = config.get("response_type",    "Detailed")
    learning_mode    = config.get("learning_mode",    "Normal")

    # 2. Student memory
    mem = get_student_memory(user_id)
    summary = build_memory_summary(mem)

    # 3. Milvus RAG (top 4 chunks, filtered by user's grade + board)
    retrieved_chunks = ""
    try:
        chunks, _ = vector_db.get_similar_documents(
            text=state.get("query", ""),
            top_k=4,
            board=user.get("board"),
            grade=user.get("grade"),
        )
        retrieved_chunks = chunks or ""
    except Exception as e:
        logger.warning(f"Milvus retrieval failed (non-fatal): {e}")

    # 4. Mirror lesson state from student_memory into top-level state
    current_topic    = mem.get("current_topic")
    lesson_subtopics = mem.get("lesson_subtopics", [])
    lesson_step      = mem.get("lesson_step", 0)

    return {
        "difficulty_level": difficulty_level,
        "response_type":    response_type,
        "learning_mode":    learning_mode,
        "student_memory":   mem,
        "memory_summary":   summary,
        "retrieved_chunks": retrieved_chunks,
        "current_topic":    current_topic,
        "lesson_subtopics": lesson_subtopics,
        "lesson_step":      lesson_step,
        "memory_delta":     {},
        "is_exiting_lesson": False,
        "repeat_requested":  False,
        "skip_composer":     False,
        "agent_output":      "",
        "last_response":     "",
    }


# ========================================
# NODE 2: smart_router (0 or 1 LLM call)
# ========================================

def smart_router(state: AgentState) -> dict:
    """
    Priority order:
      [0] awaiting_lesson_confirmation → yes/no regex (0 LLM)
      [1] repeat request → regex fast-path (0 LLM)
      [2] meta/history query → qa fast-path (0 LLM, bypasses active lesson)
      [3] small talk → regex fast-path (0 LLM, bypasses active lesson)
      [4] active lesson → LessonContextSchema (1 LLM)
      [5] general mode → RoutingSchema (1 LLM)
    """
    query    = state.get("query", "")
    awaiting = state.get("awaiting_lesson_confirmation", False)

    # [0] Lesson offer confirmation — highest priority when pending
    if awaiting:
        logger.info("smart_router: awaiting lesson confirmation")
        # Detect whether this is a mid-lesson small talk pause or an initial lesson offer
        in_lesson_pause = bool(state.get("current_topic") and state.get("lesson_subtopics"))
        if is_yes(query):
            if in_lesson_pause:
                logger.info("smart_router: student wants to resume mid-lesson")
                return {"intent": "lesson_resume", "awaiting_lesson_confirmation": False}
            logger.info("smart_router: student confirmed lesson")
            return {"intent": "lesson_confirmed", "awaiting_lesson_confirmation": False}
        elif is_no(query):
            if in_lesson_pause:
                logger.info("smart_router: student wants to close mid-lesson")
                return {"intent": "lesson_close", "awaiting_lesson_confirmation": False}
            logger.info("smart_router: student declined lesson")
            return {"intent": "lesson_declined", "awaiting_lesson_confirmation": False}
        elif in_lesson_pause:
            # New query during a mid-lesson pause — close lesson and handle the new query
            logger.info("smart_router: new query during mid-lesson pause — closing lesson and rerouting")
            return {"intent": "lesson_close_and_reroute", "awaiting_lesson_confirmation": False}
        # Ambiguous, no active lesson — clear the flag and reclassify normally below
        logger.info("smart_router: ambiguous confirmation, reclassifying")

    # [1] Repeat request fast-path
    if is_repeat_request(query):
        logger.info("smart_router: repeat request (fast path)")
        return {"intent": "repeat", "repeat_requested": True,
                "awaiting_lesson_confirmation": False}

    current_topic    = state.get("current_topic")
    lesson_subtopics = state.get("lesson_subtopics", [])
    lesson_step      = state.get("lesson_step", 0)
    in_active_lesson = bool(current_topic and lesson_subtopics)
    recent_messages  = _format_recent_messages(state.get("messages", []))

    # [2] Meta/history query — always use qa so memory_summary can answer it
    if is_meta_query(query):
        logger.info("smart_router: meta/history query (fast path)")
        return {
            "intent":                     "qa",
            "topic_slug":                 None,
            "topic_name":                 None,
            "diagnosis":                  "Student is asking about their study history or progress.",
            "awaiting_lesson_confirmation": False,
        }

    # [3] Small talk fast-path — runs before lesson context to avoid misrouting greetings
    if is_small_talk(query):
        logger.info("smart_router: small talk (fast path)")
        return {
            "intent":                     "small_talk",
            "topic_slug":                 None,
            "topic_name":                 None,
            "diagnosis":                  "Student is making casual conversation.",
            "awaiting_lesson_confirmation": False,
        }

    # [4] Active lesson — use LessonContextSchema
    if in_active_lesson:
        logger.info(f"smart_router: active lesson '{current_topic}' → LessonContextSchema")
        try:
            current_subtopic = (
                lesson_subtopics[lesson_step]
                if lesson_step < len(lesson_subtopics)
                else lesson_subtopics[-1]
            )
            prompt = LESSON_CONTEXT_PROMPT.format(
                persona=TUTOR_PERSONA,
                current_topic=current_topic,
                lesson_step=lesson_step + 1,
                total_steps=len(lesson_subtopics),
                current_subtopic=current_subtopic,
                recent_messages=recent_messages,
                query=query,
            )
            response = llm_with_lesson_context_tool.invoke(prompt)
            if response.tool_calls:
                data = response.tool_calls[0]["args"]
                return {
                    "intent":                     data.get("intent", "evaluate"),
                    "is_exiting_lesson":          data.get("is_exiting_lesson", False),
                    "repeat_requested":           data.get("repeat_requested", False),
                    "awaiting_lesson_confirmation": False,
                }
        except Exception as e:
            logger.error(f"smart_router LessonContextSchema error: {e}")
        return {"intent": "evaluate", "awaiting_lesson_confirmation": False}

    # [5] General mode — RoutingSchema
    logger.info("smart_router: general routing → RoutingSchema")
    try:
        prompt = ROUTING_PROMPT.format(
            persona=TUTOR_PERSONA,
            memory_summary=state.get("memory_summary", "No prior history."),
            recent_messages=recent_messages,
            query=query,
        )
        response = llm_with_routing_tool.invoke(prompt)
        if response.tool_calls:
            data = response.tool_calls[0]["args"]
            return {
                "intent":                     data.get("intent", "qa"),
                "topic_slug":                 data.get("topic_slug"),
                "topic_name":                 data.get("topic_name"),
                "diagnosis":                  data.get("diagnosis", ""),
                "awaiting_lesson_confirmation": False,
            }
    except Exception as e:
        logger.error(f"smart_router RoutingSchema error: {e}")

    return {"intent": "qa", "topic_slug": None, "topic_name": None, "diagnosis": "",
            "awaiting_lesson_confirmation": False}


# ========================================
# NODE 3: responder (1–2 LLM calls)
# ========================================

def responder(state: AgentState) -> dict:
    """
    Generates the educational content based on intent.
    Paths: small_talk | qa | teach (new/active) | evaluate | repeat | exit_lesson
    """
    intent           = state.get("intent", "qa")
    query            = state.get("query", "")
    user             = state.get("user", {})
    grade            = user.get("grade", "")
    board            = user.get("board", "")
    difficulty_level = state.get("difficulty_level", "Intermediate")
    learning_mode    = state.get("learning_mode", "Normal")
    memory_summary   = state.get("memory_summary", "No prior history.")
    retrieved_chunks = state.get("retrieved_chunks", "")
    current_topic    = state.get("current_topic")
    lesson_subtopics = state.get("lesson_subtopics", [])
    lesson_step      = state.get("lesson_step", 0)
    topic_slug       = state.get("topic_slug")
    topic_name       = state.get("topic_name") or state.get("topic_slug", query[:60])
    last_explanation = state.get("last_explanation", "")
    memory_delta     = state.get("memory_delta", {})
    recent_messages  = _format_recent_messages(state.get("messages", []))
    in_active_lesson = bool(current_topic and lesson_subtopics)

    # ── repeat: 0 LLM calls ─────────────────────────────────────────
    if state.get("repeat_requested") or intent == "repeat":
        if last_explanation:
            prefix = random.choice([
                "Sure, one moment. ",
                "Of course, here it is again. ",
                "No problem, I will repeat that. ",
            ])
            output = prefix + last_explanation
        else:
            output = "I do not have anything to repeat yet. Let us continue!"
        return {
            "agent_output": output,
            "skip_composer": True,
            "last_response": _strip_tts_symbols(output),
        }

    # ── exit lesson ──────────────────────────────────────────────────
    if state.get("is_exiting_lesson"):
        completed = lesson_step
        total     = len(lesson_subtopics)
        prompt = LESSON_EXIT_PROMPT.format(
            persona=TUTOR_PERSONA,
            current_topic=current_topic or "the lesson",
            completed_steps=completed,
            total_steps=total,
        )
        output = llm.invoke(prompt).content
        memory_delta["lesson_exited"] = True
        return {
            "agent_output": output,
            "memory_delta": memory_delta,
        }

    # ── small_talk ─────────────────────────────────────────────────────
    if intent == "small_talk":
        if in_active_lesson:
            # Mid-lesson small talk: respond casually + ask if they want to continue
            output = llm.invoke(
                SMALL_TALK_MID_LESSON_PROMPT.format(
                    query=query,
                    current_topic=current_topic,
                )
            ).content
            return {
                "agent_output":               output,
                "last_explanation":           output,
                "awaiting_lesson_confirmation": True,
            }
        output = llm.invoke(SMALL_TALK_PROMPT.format(query=query)).content
        return {"agent_output": output}

    # ── qa: RAG-backed direct answer ─────────────────────────────────
    if intent == "qa":
        prompt = QA_PROMPT.format(
            persona=TUTOR_PERSONA,
            memory_summary=memory_summary,
            recent_messages=recent_messages,
            query=query,
            retrieved_chunks=retrieved_chunks or "No additional context available.",
        )
        output = llm.invoke(prompt).content
        if topic_slug:
            memory_delta.setdefault("topics_touched", []).append(topic_slug)
        return {
            "agent_output": output,
            "memory_delta": memory_delta,
        }

    # ── lesson_declined: student said no to initial lesson offer ───────
    if intent == "lesson_declined":
        output = "No problem at all! Feel free to ask me anything else whenever you are ready."
        return {
            "agent_output":               output,
            "last_response":              output,
            "skip_composer":              True,
            "awaiting_lesson_confirmation": False,
        }

    # ── lesson_resume: student said yes after mid-lesson small talk ───
    if intent == "lesson_resume":
        current_subtopic = (
            lesson_subtopics[lesson_step]
            if lesson_step < len(lesson_subtopics)
            else lesson_subtopics[-1]
        )
        prompt = LESSON_RESUME_PROMPT.format(
            persona=TUTOR_PERSONA,
            current_topic=current_topic,
            lesson_step=lesson_step + 1,
            total_steps=len(lesson_subtopics),
            current_subtopic=current_subtopic,
            last_explanation=last_explanation or "Let us continue from where we left off.",
        )
        output = llm.invoke(prompt).content
        return {
            "agent_output":     output,
            "last_explanation": last_explanation,  # preserve so repeat still works
        }

    # ── lesson_close: student said no after mid-lesson small talk ─────
    if intent == "lesson_close":
        prompt = LESSON_EXIT_PROMPT.format(
            persona=TUTOR_PERSONA,
            current_topic=current_topic or "the lesson",
            completed_steps=lesson_step,
            total_steps=len(lesson_subtopics),
        )
        output = llm.invoke(prompt).content
        memory_delta["lesson_exited"] = True
        return {
            "agent_output":      output,
            "memory_delta":      memory_delta,
            "current_topic":     None,
            "lesson_subtopics":  [],
            "lesson_step":       0,
            "last_explanation":  "",
        }

    # ── lesson_close_and_reroute: new query during mid-lesson pause ───
    if intent == "lesson_close_and_reroute":
        memory_delta["lesson_exited"] = True
        # Briefly close the lesson, then handle the new query
        close_phrase = f"Okay, putting the lesson on {current_topic} on hold for now. "
        # Re-classify the new query to give the right kind of answer
        new_intent = "qa"
        new_topic_slug = None
        new_topic_name = None
        try:
            reroute_prompt = ROUTING_PROMPT.format(
                persona=TUTOR_PERSONA,
                memory_summary=memory_summary,
                recent_messages=recent_messages,
                query=query,
            )
            reroute_resp = llm_with_routing_tool.invoke(reroute_prompt)
            if reroute_resp.tool_calls:
                rdata          = reroute_resp.tool_calls[0]["args"]
                new_intent     = rdata.get("intent", "qa")
                new_topic_slug = rdata.get("topic_slug")
                new_topic_name = rdata.get("topic_name")
        except Exception as e:
            logger.error(f"lesson_close_and_reroute routing error: {e}")

        if new_intent == "small_talk":
            query_output = llm.invoke(SMALL_TALK_PROMPT.format(query=query)).content
            output = close_phrase + query_output
            return {
                "agent_output":     output,
                "memory_delta":     memory_delta,
                "current_topic":    None,
                "lesson_subtopics": [],
                "lesson_step":      0,
                "last_explanation": "",
            }
        elif new_intent == "teach":
            offer_prompt = BRIEF_OFFER_PROMPT.format(
                persona=TUTOR_PERSONA,
                memory_summary=memory_summary,
                query=query,
                topic_name=new_topic_name or query[:60],
            )
            query_output = llm.invoke(offer_prompt).content
            if new_topic_slug:
                memory_delta.setdefault("topics_touched", []).append(new_topic_slug)
            output = close_phrase + query_output
            return {
                "agent_output":               output,
                "last_explanation":           query_output,
                "awaiting_lesson_confirmation": True,
                "topic_name":                 new_topic_name,
                "topic_slug":                 new_topic_slug,
                "memory_delta":               memory_delta,
                "current_topic":              None,
                "lesson_subtopics":           [],
                "lesson_step":                0,
            }
        else:  # qa
            qa_prompt = QA_PROMPT.format(
                persona=TUTOR_PERSONA,
                memory_summary=memory_summary,
                recent_messages=recent_messages,
                query=query,
                retrieved_chunks=retrieved_chunks or "No additional context available.",
            )
            query_output = llm.invoke(qa_prompt).content
            if new_topic_slug:
                memory_delta.setdefault("topics_touched", []).append(new_topic_slug)
            output = close_phrase + query_output
            return {
                "agent_output":     output,
                "memory_delta":     memory_delta,
                "current_topic":    None,
                "lesson_subtopics": [],
                "lesson_step":      0,
                "last_explanation": "",
            }

    # ── teach: no active lesson → brief answer + offer (NOT plan yet) ─
    if intent == "teach" and not lesson_subtopics:
        logger.info(f"responder: teach offer — '{topic_name}'")
        offer_prompt = BRIEF_OFFER_PROMPT.format(
            persona=TUTOR_PERSONA,
            memory_summary=memory_summary,
            query=query,
            topic_name=topic_name or query[:60],
        )
        output = llm.invoke(offer_prompt).content
        if topic_slug:
            memory_delta.setdefault("topics_touched", []).append(topic_slug)
        return {
            "agent_output":               output,
            "last_explanation":           output,
            "awaiting_lesson_confirmation": True,
            "memory_delta":               memory_delta,
        }

    # ── lesson_confirmed: student said yes → plan + start step 1 ─────
    if intent == "lesson_confirmed":
        logger.info(f"responder: lesson confirmed — planning '{topic_name}'")
        try:
            plan_prompt = LESSON_PLAN_PROMPT_V2.format(
                grade=grade,
                board=board,
                difficulty_level=difficulty_level,
                topic_name=topic_name or query[:60],
                max_steps=MAX_STEPS,
            )
            plan_response = llm_with_lesson_plan_tool.invoke(plan_prompt)
            if plan_response.tool_calls:
                plan_data    = plan_response.tool_calls[0]["args"]
                refined_name = plan_data.get("topic", topic_name)
                subtopics    = plan_data.get("steps", [])
            else:
                refined_name = topic_name or query[:60]
                subtopics    = [
                    f"Introduction to {refined_name}",
                    f"Core concepts of {refined_name}",
                    f"Applications of {refined_name}",
                ]
        except Exception as e:
            logger.error(f"Lesson plan error: {e}")
            refined_name = topic_name or query[:60]
            subtopics    = [
                f"Introduction to {refined_name}",
                f"Core concepts of {refined_name}",
                f"Applications of {refined_name}",
            ]

        subtopics = subtopics[:MAX_STEPS]
        if len(subtopics) < 3:
            subtopics += [f"Further aspects of {refined_name}"] * (3 - len(subtopics))

        intro_prompt = LESSON_INTRO_PROMPT.format(
            topic_name=refined_name,
            grade=grade,
            board=board,
            difficulty_level=difficulty_level,
            total_steps=len(subtopics),
            first_subtopic=subtopics[0],
        )
        output = llm.invoke(intro_prompt).content

        memory_delta["lesson_started"] = {
            "topic_name": refined_name,
            "topic_slug": topic_slug or refined_name.lower().replace(" ", "_"),
            "subtopics":  subtopics,
        }
        memory_delta.setdefault("topics_touched", []).append(
            topic_slug or refined_name.lower().replace(" ", "_")
        )

        return {
            "agent_output":               output,
            "last_explanation":           output,
            "current_topic":              refined_name,
            "lesson_subtopics":           subtopics,
            "lesson_step":                0,
            "awaiting_lesson_confirmation": False,
            "memory_delta":               memory_delta,
        }

    # ── teach: active lesson → explain current step (friction-aware) ──
    if intent == "teach":

        # Active lesson → explain current step (friction-aware)
        current_subtopic = (
            lesson_subtopics[lesson_step]
            if lesson_step < len(lesson_subtopics)
            else lesson_subtopics[-1]
        )
        friction_count = (
            state.get("student_memory", {})
            .get("friction", {})
            .get(topic_slug or "", {})
            .get("attempts", 0)
        )
        friction_note = ""
        if friction_count >= 2:
            friction_note = (
                f"IMPORTANT: This student has struggled with this concept {friction_count} times. "
                "The previous explanations did not fully land. "
                "Use a COMPLETELY DIFFERENT approach — new analogy, new entry point, simpler language. "
                "Do not repeat what was said before."
            )

        prompt = EXPLAIN_PROMPT.format(
            persona=TUTOR_PERSONA,
            memory_summary=memory_summary,
            recent_messages=recent_messages,
            current_subtopic=current_subtopic,
            lesson_step=lesson_step + 1,
            total_steps=len(lesson_subtopics),
            current_topic=current_topic,
            grade=grade,
            board=board,
            difficulty_level=difficulty_level,
            learning_mode=learning_mode,
            retrieved_chunks=retrieved_chunks or "No additional context available.",
            friction_note=friction_note,
        )
        output = llm.invoke(prompt).content
        memory_delta.setdefault("topics_touched", []).append(topic_slug or "")

        return {
            "agent_output":     output,
            "last_explanation": output,
            "memory_delta":     memory_delta,
        }

    # ── evaluate ─────────────────────────────────────────────────────
    if intent == "evaluate":
        current_subtopic = (
            lesson_subtopics[lesson_step]
            if lesson_step < len(lesson_subtopics)
            else lesson_subtopics[-1] if lesson_subtopics else query
        )

        try:
            eval_prompt = EVAL_PROMPT_V2.format(
                current_topic=current_topic or topic_name or "the topic",
                current_subtopic=current_subtopic,
                last_explanation=last_explanation or "the previous question",
                user_response=query,
                recent_messages=recent_messages,
            )
            eval_response = llm_with_eval_tool.invoke(eval_prompt)
            if eval_response.tool_calls:
                eval_data   = eval_response.tool_calls[0]["args"]
                is_correct  = eval_data.get("is_correct", True)
                feedback    = eval_data.get("feedback", "")
            else:
                is_correct, feedback = True, "Good effort! Let us continue."
        except Exception as e:
            logger.error(f"Eval error: {e}")
            is_correct, feedback = True, "Good effort! Let us continue."

        # Record evaluation in delta
        ev_topic_slug = (
            topic_slug
            or (current_topic or "").lower().replace(" ", "_")
        )
        memory_delta["evaluation"] = {
            "topic_slug": ev_topic_slug,
            "correct":    is_correct,
            "step":       lesson_step,
        }
        memory_delta.setdefault("topics_touched", []).append(ev_topic_slug)

        # Advance step
        next_step = lesson_step + 1
        lesson_done = next_step >= len(lesson_subtopics)

        if lesson_done:
            next_context = (
                f"The student has finished all {len(lesson_subtopics)} subtopics "
                f"in the lesson on '{current_topic}'. "
                "Wrap up with a warm congratulations."
            )
            memory_delta["lesson_ended"] = True
        else:
            next_subtopic = lesson_subtopics[next_step]
            next_context = f"Now begin teaching the next subtopic: '{next_subtopic}'."

        bridge_prompt = FEEDBACK_BRIDGE_PROMPT.format(
            persona=TUTOR_PERSONA,
            current_subtopic=current_subtopic,
            feedback=feedback,
            next_context=next_context,
        )
        output = llm.invoke(bridge_prompt).content

        new_subtopics = [] if lesson_done else lesson_subtopics
        new_topic     = None if lesson_done else current_topic

        return {
            "agent_output":      output,
            "last_explanation":  output,
            "lesson_step":       next_step if not lesson_done else lesson_step,
            "current_topic":     new_topic,
            "lesson_subtopics":  new_subtopics,
            "memory_delta":      memory_delta,
        }

    # Fallback: treat as small talk
    output = llm.invoke(SMALL_TALK_PROMPT.format(query=query)).content
    return {"agent_output": output}


# ========================================
# NODE 4: response_composer (1 LLM call) + memory_updater (0 LLM)
# ========================================

def response_composer(state: AgentState) -> dict:
    """
    Applies the tutor's personality voice and ensures TTS compatibility.
    Then writes the memory_delta to the student_memory MongoDB document.
    """
    user             = state.get("user", {})
    user_id          = str(user.get("_id", ""))
    grade            = user.get("grade", "")
    board            = user.get("board", "")
    difficulty_level = state.get("difficulty_level", "Intermediate")
    learning_mode    = state.get("learning_mode", "Normal")
    agent_output     = state.get("agent_output", "")

    # Skip personality LLM call for zero-cost paths (repeat requests)
    if state.get("skip_composer"):
        final = _strip_tts_symbols(agent_output)
        _dispatch_memory_write(user_id, state)
        return {
            "last_response": final,
            "messages": [AIMessage(content=final)],
        }

    # Personality + TTS pass
    try:
        prompt = COMPOSER_PROMPT.format(
            persona=TUTOR_PERSONA,
            grade=grade,
            board=board,
            difficulty_level=difficulty_level,
            learning_mode=learning_mode,
            agent_output=agent_output,
        )
        final = llm.invoke(prompt).content
    except Exception as e:
        logger.error(f"Composer error (falling back to raw output): {e}")
        final = agent_output

    final = _strip_tts_symbols(final)

    # Fire memory write in background — does not block response delivery
    _dispatch_memory_write(user_id, state)

    return {
        "last_response": final,
        "messages": [AIMessage(content=final)],
    }


def _dispatch_memory_write(user_id: str, state: AgentState) -> None:
    """
    Snapshot the memory-relevant fields and fire _write_student_memory
    in a daemon thread so it never blocks response delivery.
    """
    snapshot = {
        "student_memory":  dict(state.get("student_memory") or {}),
        "memory_delta":    dict(state.get("memory_delta") or {}),
        "lesson_step":     state.get("lesson_step", 0),
        "session_id":      state.get("session_id", ""),
        "query":           state.get("query", ""),
        "agent_output":    state.get("agent_output", ""),
    }
    t = threading.Thread(
        target=_write_student_memory,
        args=(user_id, snapshot),
        daemon=True,
    )
    t.start()


def _write_student_memory(user_id: str, state: dict) -> None:
    """
    Background task: LLM quality gate → apply delta → persist to MongoDB.
    Runs in a daemon thread so it never blocks response delivery.
    """
    if not user_id:
        return
    try:
        mem   = dict(state.get("student_memory") or {})
        delta = dict(state.get("memory_delta") or {})

        # 1. LLM quality gate — enriches delta with filter decisions
        delta = filter_and_enrich_delta(delta, state)

        # 2. Apply filtered + enriched delta to the memory doc
        mem = apply_memory_delta(mem, delta, state)

        # 3. Persist
        upsert_student_memory(user_id, mem)
        logger.info(f"Student memory written for user {user_id}")
    except Exception as e:
        logger.error(f"Memory write failed (non-fatal): {e}")


# ========================================
# GRAPH ASSEMBLY
# ========================================

def build_agent():
    """Build and compile the linear 4-node LangGraph workflow."""
    workflow = StateGraph(AgentState)

    workflow.add_node("context_loader",    context_loader)
    workflow.add_node("smart_router",      smart_router)
    workflow.add_node("responder",         responder)
    workflow.add_node("response_composer", response_composer)

    workflow.set_entry_point("context_loader")
    workflow.add_edge("context_loader",    "smart_router")
    workflow.add_edge("smart_router",      "responder")
    workflow.add_edge("responder",         "response_composer")
    workflow.add_edge("response_composer", END)

    app = workflow.compile(checkpointer=checkpointer)
    logger.info("Agent workflow compiled (v1 upgrade: 4-node linear graph)")
    return app


# ========================================
# SINGLETON + PUBLIC ENTRY POINT
# ========================================

_cached_agent = None


def get_agent():
    global _cached_agent
    if _cached_agent is None:
        _cached_agent = build_agent()
        logger.info("Agent graph built and cached")
    return _cached_agent


def run_agent(user: dict, query: str, session_id: str) -> str:
    """
    Run the guided learning agent. Called via asyncio.to_thread from the router.
    """
    logger.info(f"run_agent — user={user.get('_id')} query={query[:60]!r}")
    try:
        config = {"configurable": {"thread_id": session_id}}
        agent  = get_agent()

        input_state = {
            "messages": [HumanMessage(content=query)],
            "query":     query,
            "user":      user,
            "session_id": session_id,
            # Backward-compat defaults so old checkpoints don't crash.
            # NOTE: awaiting_lesson_confirmation is intentionally NOT set here —
            # it must persist from the checkpoint across turns.
            "mode":             "general",
            "topic":            "",
            "lesson_plan":      [],
            "lesson_step_legacy": 0,
            "last_action":      "initial",
            "pending_topic":    "",
            "feedback":         "",
        }

        result = agent.invoke(input_state, config=config)

        # last_response is set by response_composer; fall back to last AIMessage
        response = result.get("last_response", "")
        if not response:
            ai_messages = [m for m in result.get("messages", []) if isinstance(m, AIMessage)]
            response = ai_messages[-1].content if ai_messages else "I am here to help you learn!"

        logger.info("run_agent completed")
        return response

    except Exception as e:
        logger.error(f"run_agent error: {e}", exc_info=True)
        raise
