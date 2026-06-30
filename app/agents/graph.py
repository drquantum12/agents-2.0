"""
graph.py
─────────────────────────────────────────────
Assembles the ReAct LangGraph agent and exposes a `chat()` entrypoint.

Graph topology (replaces the old 5-node intent-routing graph):
─────────────────────────────────────────────
                   ┌────────────┐
          START ──►│ react_agent│──► END
                   └────────────┘

The react_agent node runs a proper ReAct (Reason + Act) loop:
  LLM → tool_calls? → execute tools → back to LLM → ... → final answer

Tools available inside the loop:
  signal_device_state       push WS animation frame to the device
  retrieve_curriculum_context  RAG lookup in Milvus (board/grade filtered)
  search_web                Gemini-grounded live web search
  calculate                 sandboxed math expression evaluator
  quiz_user                 generate a quiz question
  check_answer              evaluate student's quiz answer
  get_user_profile          read MongoDB user document
  update_user_profile       write a learning profile field
  set_reminder              schedule a future spoken reminder
  spaced_repeat             schedule spaced-repetition reviews
  clarify_intent            ask a structured clarifying question

MongoDB is used for:
  1. LangGraph MongoDBSaver   — persists full AgentState between turns
  2. TeacherMemoryManager     — lesson state for cross-session restore
  3. WebSearchMemoryManager   — Gemini grounding result cache
  4. UserProfileMemory        — agent observations about the student

Legacy nodes (teacher, general, web_search, orchestrator,
user_confirmation) are preserved in nodes/ for reference but are no
longer wired into the graph.
"""

import logging
from functools import partial
from typing import Optional, Callable

from pymongo import MongoClient
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.mongodb import MongoDBSaver

from app.db_utility.mongo_db import mongo_db as _mongo_db
from .state import AgentState
from .memory.teacher_memory import TeacherMemoryManager
from .memory.web_search_memory import WebSearchMemoryManager
from .memory.user_profile_memory import UserProfileMemory
from .nodes.react_agent import react_agent_node
from .tools.context import _signal_fn_var

logger = logging.getLogger(__name__)


# ── Graph factory ─────────────────────────────────────────────────────────────

def build_graph(client: MongoClient, db_name: str = "neurosattva"):
    """
    Build and compile the LangGraph ReAct agent.

    Returns:
        graph          — compiled LangGraph CompiledStateGraph
        teacher_memory — TeacherMemoryManager
        web_memory     — WebSearchMemoryManager
        profile_memory — UserProfileMemory
    """
    db = client[db_name]

    teacher_memory = TeacherMemoryManager(db)
    web_memory     = WebSearchMemoryManager(db)
    profile_memory = UserProfileMemory(db)

    # Inject memory managers into react_agent_node via partial
    _react = partial(
        react_agent_node,
        teacher_memory=teacher_memory,
        web_memory=web_memory,
    )

    # ── StateGraph ────────────────────────────────────────────────────────
    builder = StateGraph(AgentState)
    builder.add_node("react_agent", _react)
    builder.add_edge(START, "react_agent")
    builder.add_edge("react_agent", END)

    # ── MongoDB checkpointer ──────────────────────────────────────────────
    checkpointer = MongoDBSaver(client, db_name=db_name)
    graph = builder.compile(checkpointer=checkpointer)

    logger.info(
        "LangGraph ReAct agent compiled with MongoDB checkpointer (%s/%s)",
        client.address, db_name,
    )
    return graph, teacher_memory, web_memory, profile_memory


# ── Module-level singletons ───────────────────────────────────────────────────

_graph = None
_teacher_memory: Optional[TeacherMemoryManager]  = None
_web_memory:     Optional[WebSearchMemoryManager] = None
_profile_memory: Optional[UserProfileMemory]      = None


def init_agent(db_name: str = "neurosattva") -> None:
    """Call once at app startup to compile the graph and warm up memory managers."""
    global _graph, _teacher_memory, _web_memory, _profile_memory
    _graph, _teacher_memory, _web_memory, _profile_memory = build_graph(
        _mongo_db.client, db_name
    )


# ── Chat entrypoint ───────────────────────────────────────────────────────────

def chat(
    user_id:    str,
    session_id: str,
    query:      str,
    *,
    mode:       str  = "DEFAULT",
    grade:      Optional[str]  = None,
    board:      Optional[str]  = None,
    personalized: bool         = False,
    is_new_session: bool       = False,
    signal_fn:  Optional[Callable[[str], None]] = None,
) -> str:
    """
    Single entrypoint for a user turn.

    Args:
        user_id        : MongoDB user._id
        session_id     : Maps to LangGraph thread_id (checkpoint key)
        query          : Raw user message text (already transcribed by STT)
        mode           : "STRICT" | "DEFAULT"
        grade          : Student grade, e.g. "10"
        board          : Curriculum board, e.g. "CBSE"
        personalized   : Whether to personalise responses
        is_new_session : True on the first turn → restores TeacherMemory into state
        signal_fn      : Optional thread-safe callback to push WS text frames to
                         the device from within tool functions.
                         Signature: (json_str: str) -> None
                         Created by the WS handler using asyncio.run_coroutine_threadsafe.

    Returns:
        The agent's response as a plain string.
    """
    if _graph is None:
        raise RuntimeError("Agent not initialised. Call init_agent() first.")

    # Inject the signal callback into the ContextVar so all tools in this
    # thread can call it without needing it as a function parameter.
    if signal_fn is not None:
        _signal_fn_var.set(signal_fn)

    config = {"configurable": {"thread_id": session_id}}

    if is_new_session:
        # Restore lesson state from TeacherMemory for session continuity
        lesson_state = _teacher_memory.sync_to_state(user_id) if _teacher_memory else {}

        input_state: AgentState = {
            "query":               query,
            "messages":            [],
            "session_id":          session_id,
            "user_id":             user_id,
            "mode":                mode.upper(),
            "intent":              None,
            "awaiting_user_input": False,
            "grade":               grade,
            "board":               board,
            "personalized":        personalized,
            "quiz_correct_answer": None,
            "tool_call_count":     0,
            # Restore lesson fields from TeacherMemory
            **lesson_state,
        }
    else:
        # Subsequent turn — LangGraph merges with checkpoint automatically
        input_state = {
            "query":   query,
            "user_id": user_id,
            "mode":    mode.upper(),
        }

    result = _graph.invoke(input_state, config=config)

    messages = result.get("messages", [])
    if messages:
        return messages[-1].content

    return "(no response)"
