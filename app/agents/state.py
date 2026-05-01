"""
state.py
─────────────────────────────────────────────
Single source of truth for the LangGraph agent state.

Notes:
  • `messages` uses Annotated[list, operator.add] so LangGraph APPENDS
    new messages on each node return instead of replacing the whole list.
  • All lesson / teacher fields are Optional so they start as None and are
    only populated once a lesson is active.
  • `user_id` is included so every node can address MongoDB without needing
    a separate argument.
"""

import operator
from typing import Annotated, List, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    # ── Core ─────────────────────────────────────────────────────────────
    query: str                                   # current user input
    messages: Annotated[List[BaseMessage], operator.add]  # full conversation
    session_id: str                              # LangGraph thread_id
    user_id: str                                 # MongoDB user._id

    # ── Routing ──────────────────────────────────────────────────────────
    intent: Optional[str]        # EXPLANATION | GENERAL | WEB_SEARCH | CONFIRM_WITH_USER
    awaiting_user_input: bool    # True  → next turn must hit user_confirmation node

    # ── Lesson / teacher state (mirrored from TeacherMemory) ─────────────
    mode: str                    # STRICT | DEFAULT  (controls teacher behaviour)
    topic: Optional[str]         # e.g. "Neural Networks"
    lesson_plan: Optional[List[str]]   # ordered list of subtopic strings
    lesson_status: Optional[str]       # ON | OFF
    current_subtopic: Optional[str]    # subtopic currently being taught
    step_context: Optional[str]        # free-text context for the current step

    # ── User profile (loaded once at session start) ───────────────────────
    grade: Optional[str]         # e.g. "10" – used to calibrate explanation depth
    board: Optional[str]         # e.g. "CBSE" – curriculum context
    personalized: bool           # whether to personalise responses
