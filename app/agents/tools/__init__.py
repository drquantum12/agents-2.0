"""
tools/__init__.py
─────────────────────────────────────────────
Exports all ReAct agent tools and the ALL_TOOLS list used by react_agent_node
to bind tools to the LLM.

Tool ordering matters for the LLM's default preference — more frequently
useful tools are listed first.
"""
from .device_tools  import signal_device_state
from .rag_tool      import retrieve_curriculum_context
from .search_tool   import search_web
from .math_tool     import calculate
from .quiz_tools    import quiz_user, check_answer
from .profile_tools import get_user_profile, update_user_profile
from .memory_tools  import set_reminder, spaced_repeat, clarify_intent
from .lesson_tools  import start_lesson, advance_subtopic, end_lesson, flag_weak_concept

ALL_TOOLS = [
    signal_device_state,
    retrieve_curriculum_context,
    search_web,
    calculate,
    quiz_user,
    check_answer,
    get_user_profile,
    update_user_profile,
    set_reminder,
    spaced_repeat,
    clarify_intent,
    # ── Lesson / study-session tools ──
    start_lesson,
    advance_subtopic,
    end_lesson,
    flag_weak_concept,
]

__all__ = [
    "ALL_TOOLS",
    "signal_device_state",
    "retrieve_curriculum_context",
    "search_web",
    "calculate",
    "quiz_user",
    "check_answer",
    "get_user_profile",
    "update_user_profile",
    "set_reminder",
    "spaced_repeat",
    "clarify_intent",
    "start_lesson",
    "advance_subtopic",
    "end_lesson",
    "flag_weak_concept",
]
