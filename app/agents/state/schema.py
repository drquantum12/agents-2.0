"""
AgentState — the single source of truth for all state persisted across turns.
Stored by MongoDBSaver (msgpack) keyed on thread_id = session_id.
"""

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    # ---- conversation history (appended each turn by LangGraph) ----
    messages: Annotated[list[BaseMessage], operator.add]

    # ---- per-turn routing (set by intent_router) ----
    route: str       # "general" | "teacher" | "stop_teacher"
    sub_intent: str  # "new_topic" | "continue" | "digress" | "digress_resume" | "digress_exit"

    # ---- mode (persists across turns) ----
    mode: str  # "general" | "teacher"

    # ---- teacher-mode lesson state ----
    active_topic: str | None
    lesson_plan: list[str]
    current_step: int
    step_context: list[dict]
    pending_resume: bool

    # ---- lesson-offer confirmation flow ----
    awaiting_lesson_confirmation: bool
    pending_topic: str | None

    # ---- long-term student memory ----
    student_profile: dict
    world_model_dirty: bool

    # ---- session metadata ----
    user_id: str
