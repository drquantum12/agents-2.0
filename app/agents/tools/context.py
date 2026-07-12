"""
tools/context.py
─────────────────────────────────────────────
Thread-local ContextVars shared across all agent tools.

These are set by react_agent_node before the ReAct loop begins and are
readable by every tool function during that loop.

Why ContextVar instead of function arguments?
  LangChain @tool functions have a fixed signature (only their declared
  args). Injecting cross-cutting concerns (WS callback, memory managers,
  user context) via ContextVar keeps tool signatures clean while still
  being thread-safe.

asyncio.to_thread() calls contextvars.copy_context() when spawning the
thread, so any ContextVar set in the async handler before the to_thread()
call is visible inside the thread — and by extension inside every tool
invoked from within that thread.
"""
from contextvars import ContextVar
from typing import Optional, Callable

# ── WebSocket signal callback ─────────────────────────────────────────────────
# Signature: (json_str: str) -> None
# Blocks the calling thread briefly while the WS send completes on the
# event loop (via asyncio.run_coroutine_threadsafe). Set by chat() from
# the value passed in by the WS handler.
_signal_fn_var: ContextVar[Optional[Callable[[str], None]]] = ContextVar(
    "agent_signal_fn", default=None
)

# ── Tool → state patch accumulator ───────────────────────────────────────────
# react_agent_node initialises this to a fresh {} at the start of each turn.
# Tools that need to mutate LangGraph state (quiz_user, check_answer,
# clarify_intent) write their patches here.
# react_agent_node reads the dict after the loop and merges it into the
# returned state delta.
_state_patches_var: ContextVar[Optional[dict]] = ContextVar(
    "agent_state_patches", default=None
)

# ── Lightweight user context ──────────────────────────────────────────────────
# Shape: {"user_id": str, "board": Optional[str], "grade": Optional[str]}
# Populated from AgentState by react_agent_node so tools don't re-query
# MongoDB for fields already in state.
_user_context_var: ContextVar[Optional[dict]] = ContextVar(
    "agent_user_context", default=None
)

# ── Memory manager references ─────────────────────────────────────────────────
# Shape: {"teacher": TeacherMemoryManager, "web": WebSearchMemoryManager}
# Injected by react_agent_node (which receives them via functools.partial).
_memory_var: ContextVar[Optional[dict]] = ContextVar(
    "agent_memory_managers", default=None
)

# ── Active lesson state ───────────────────────────────────────────────────────
# Shape: {
#   "lesson_status":    "ON" | "OFF",
#   "topic":            str | None,
#   "lesson_plan":      list[str] | None,   # ordered subtopic strings
#   "subtopic_idx":     int,                # 0-based current position
#   "mode":             "STRICT" | "DEFAULT",
# }
# Populated from AgentState by react_agent_node so lesson tools can read
# current position and plan without needing to query MongoDB mid-loop.
_lesson_state_var: ContextVar[Optional[dict]] = ContextVar(
    "agent_lesson_state", default=None
)
