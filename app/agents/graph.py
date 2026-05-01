"""
graph.py
─────────────────────────────────────────────
Assembles the LangGraph agent and exposes a `chat()` entrypoint.

Graph topology
──────────────
                   ┌─────────┐
          START ──►│orchestr-│
                   │  ator   │
                   └────┬────┘
                        │  (conditional on state["intent"])
          ┌─────────────┼─────────────┬──────────────────┐
          ▼             ▼             ▼                   ▼
      [general]    [teacher]    [web_search]   [user_confirmation]
          │             │             │                   │
          └─────────────┴─────────────┴───────────────────┘
                                    ▼
                                   END

MongoDB is used for two purposes:
  1. LangGraph MongoDBSaver  — persists full AgentState between turns
                               (keyed by session_id / thread_id)
  2. TeacherMemoryManager    — mirrors lesson state for cross-session restore
  3. WebSearchMemoryManager  — caches search results

Session restore strategy
─────────────────────────
On the FIRST turn of a session:
  • Load TeacherMemory for the user → inject into initial state
  • This ensures a returning student continues their lesson even if the
    LangGraph checkpoint was cleared.

On subsequent turns:
  • Just pass `{"query": ..., "user_id": ...}` — LangGraph merges with checkpoint.
"""

import logging
from functools import partial
from typing import Optional

from pymongo import MongoClient
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.mongodb import MongoDBSaver
from app.db_utility.mongo_db import mongo_db as _mongo_db
from .state import AgentState
from .memory.teacher_memory import TeacherMemoryManager
from .memory.web_search_memory import WebSearchMemoryManager

from .nodes.orchestrator       import orchestrator_node
from .nodes.teacher            import teacher_node
from .nodes.general            import general_node
from .nodes.web_search         import web_search_node
from .nodes.user_confirmation  import user_confirmation_node

logger = logging.getLogger(__name__)


# ── Routing ───────────────────────────────────────────────────────────────────

def _route_by_intent(state: AgentState) -> str:
    """
    Conditional edge called after orchestrator_node.
    Maps state["intent"] → node name string.
    """
    intent = (state.get("intent") or "GENERAL").upper()
    return {
        "EXPLANATION":        "teacher",
        "GENERAL":            "general",
        "WEB_SEARCH":         "web_search",
        "CONFIRM_WITH_USER":  "user_confirmation",
    }.get(intent, "general")


# ── Graph factory ─────────────────────────────────────────────────────────────

def build_graph(client: MongoClient, db_name: str = "neurosattva"):
    """
    Build and compile the LangGraph agent.

    Returns:
        graph          — compiled LangGraph CompiledStateGraph
        teacher_memory — TeacherMemoryManager (for use in chat())
        web_memory     — WebSearchMemoryManager
    """
    db     = client[db_name]

    teacher_memory = TeacherMemoryManager(db)
    web_memory     = WebSearchMemoryManager(db)

    # Bind memory managers to nodes that need them
    _teacher     = partial(teacher_node,           teacher_memory=teacher_memory)
    _web         = partial(web_search_node,        web_memory=web_memory)
    _confirm     = partial(user_confirmation_node, teacher_memory=teacher_memory)

    # ── StateGraph ────────────────────────────────────────────────────────
    builder = StateGraph(AgentState)

    builder.add_node("orchestrator",      orchestrator_node)
    builder.add_node("teacher",           _teacher)
    builder.add_node("general",           general_node)
    builder.add_node("web_search",        _web)
    builder.add_node("user_confirmation", _confirm)

    # Edges
    builder.add_edge(START, "orchestrator")

    builder.add_conditional_edges(
        "orchestrator",
        _route_by_intent,
        {
            "teacher":           "teacher",
            "general":           "general",
            "web_search":        "web_search",
            "user_confirmation": "user_confirmation",
        },
    )

    for terminal in ["teacher", "general", "web_search", "user_confirmation"]:
        builder.add_edge(terminal, END)

    # ── MongoDB checkpointer ──────────────────────────────────────────────
    checkpointer = MongoDBSaver(client, db_name=db_name)
    graph = builder.compile(checkpointer=checkpointer)

    logger.info("LangGraph agent compiled with MongoDB checkpointer (%s/%s)", client.address, db_name)
    return graph, teacher_memory, web_memory


# ── Chat entrypoint ───────────────────────────────────────────────────────────

# Build once at import time (or call explicitly in your app startup)
_graph = None
_teacher_memory: Optional[TeacherMemoryManager] = None
_web_memory: Optional[WebSearchMemoryManager] = None

def init_agent(db_name: str = "neurosattva") -> None:
    """Call once at app startup."""
    global _graph, _teacher_memory, _web_memory
    _graph, _teacher_memory, _web_memory = build_graph(_mongo_db.client, db_name)

def chat(
    user_id:    str,
    session_id: str,
    query:      str,
    *,
    mode:       str  = "DEFAULT",
    grade:      Optional[str] = None,
    board:      Optional[str] = None,
    personalized: bool = False,
    is_new_session: bool = False,
) -> str:
    """
    Single entrypoint for a user turn.

    Args:
        user_id       : MongoDB user._id
        session_id    : Maps to LangGraph thread_id (= LangGraph checkpoint key)
        query         : Raw user message text
        mode          : "STRICT" | "DEFAULT"  (can be toggled per-session)
        grade         : Used to calibrate explanation depth (optional)
        board         : Curriculum context, e.g. "CBSE" (optional)
        personalized  : Whether to personalise responses
        is_new_session: Pass True on the first turn of a brand-new session
                        to restore TeacherMemory into state.

    Returns:
        The tutor's response as a plain string.
    """
    if _graph is None:
        raise RuntimeError("Agent not initialised. Call init_agent() first.")

    config = {"configurable": {"thread_id": session_id}}

    if is_new_session:
        # Restore lesson state from MongoDB so the student can continue
        lesson_state = _teacher_memory.sync_to_state(user_id) if _teacher_memory else {}

        initial_state: AgentState = {
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
            # Restore from TeacherMemory (all None if no previous lesson)
            **lesson_state,
        }
        input_state = initial_state
    else:
        # Subsequent turn — just update the mutable fields.
        # LangGraph loads the rest from the checkpoint.
        input_state = {
            "query":   query,
            "user_id": user_id,
            "mode":    mode.upper(),
        }

    result = _graph.invoke(input_state, config=config)

    # The last message in state is the tutor's reply
    messages = result.get("messages", [])
    if messages:
        return messages[-1].content

    return "(no response)"  # should never happen
