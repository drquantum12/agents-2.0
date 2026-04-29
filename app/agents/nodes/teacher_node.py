"""
teacher_node — Socratic mentor response generator.

Lesson lifecycle
────────────────
new_topic (triggered once per learning event)
  LLM call 1  build_plan_prompt   → dedicated subtopic breakdown → stored in lesson_plan
  LLM call 2  build_teach_step_prompt → teach subtopic 1 with its curriculum context
  State init  subtopic_status = ["in_progress", "pending", ...]

continue (every subsequent student turn while in teacher mode)
  Pre-step    fetch_for_query(next_subtopic) — cheap vector DB call, no LLM
  LLM call    build_continue_prompt → assess + (re-explain OR teach next subtopic)
  On understood: subtopic_status[current] = "completed", status[next] = "in_progress"
                 current_step advances, step_context updated — both persisted by checkpointer
  On partial/not_understood: state unchanged, student stays on current subtopic

Break-out paths (stop_teacher / digress_exit)
  All lesson state cleared: lesson_plan=[], subtopic_status=[], current_step=0,
  step_context=[], active_topic=None → mode="general"
  New learning event starts fresh with new subtopics.

digress / digress_resume
  Answer off-topic, set pending_resume; on yes restore to current subtopic position.
"""

import json
import logging

from langchain_core.messages import AIMessage

from app.agents.llm import llm
from app.agents.nodes.retrieve_context import fetch_for_query
from app.agents.prompts.teacher import (
    build_continue_prompt,
    build_digress_prompt,
    build_plan_prompt,
    build_resume_prompt,
    build_teach_step_prompt,
)
from app.agents.state.schema import AgentState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public node function
# ---------------------------------------------------------------------------

def teacher_node(state: AgentState) -> dict:
    """Dispatch to the appropriate teaching sub-handler."""
    sub_intent = state.get("sub_intent", "")
    student_profile = state.get("student_profile", {})
    active_topic = state.get("active_topic", "")
    lesson_plan = state.get("lesson_plan", [])
    subtopic_status = state.get("subtopic_status", [])
    current_step = state.get("current_step", 0)
    step_context = state.get("step_context", [])

    logger.info(
        "teacher_node: sub_intent=%s, step=%d/%d, status=%s",
        sub_intent, current_step, len(lesson_plan), subtopic_status,
    )

    if sub_intent == "new_topic":
        return _handle_new_topic(student_profile, active_topic, step_context)
    if sub_intent == "continue":
        return _handle_continue(
            student_profile, active_topic, lesson_plan,
            subtopic_status, current_step, step_context,
        )
    if sub_intent == "digress":
        return _handle_digress(active_topic, current_step, lesson_plan)
    if sub_intent == "digress_resume":
        return _handle_digress_resume(active_topic, current_step, lesson_plan)
    if sub_intent == "digress_exit":
        return _handle_digress_exit(state)

    return {"messages": [AIMessage(content="Let me help you with your lesson.")]}


# ---------------------------------------------------------------------------
# Sub-handlers
# ---------------------------------------------------------------------------

def _parse_plan(raw: str) -> list | None:
    """
    Extract a JSON array from the plan LLM response.
    Tolerates markdown code fences and surrounding prose.
    """
    text = raw.strip()

    # Strip ```json … ``` fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        inner = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(inner).strip()

    # Try direct parse first
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except Exception:
        pass

    # Fall back to finding the first [...] in the text
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        try:
            result = json.loads(text[start : end + 1])
            if isinstance(result, list):
                return result
        except Exception:
            pass

    return None


def _handle_new_topic(student_profile: dict, active_topic: str, step_context: list) -> dict:
    """
    LLM call 1 — generate the subtopic breakdown (dedicated, no teaching mixed in).
    LLM call 2 — teach subtopic 0 using the already-fetched topic-level context.

    Initialises subtopic_status so the checkpointer tracks per-subtopic completion
    from this point forward.  A fresh learning event always resets this list.
    """
    logger.info("new_topic: %s", active_topic)

    fallback_plan = [
        f"Introduction to {active_topic}",
        f"Core concepts of {active_topic}",
        f"Applications of {active_topic}",
    ]

    context_text = "\n".join(c.get("explanation", "") for c in step_context)

    # ── LLM call 1: subtopic breakdown ───────────────────────────────────
    plan_prompt = build_plan_prompt(
        active_topic=active_topic,
        grade=student_profile.get("grade", 10),
        context_text=context_text,
    )

    lesson_plan = fallback_plan
    try:
        raw_plan = llm.invoke(plan_prompt).content
        parsed = _parse_plan(raw_plan)
        if parsed and 2 <= len(parsed) <= 5:
            lesson_plan = [str(s).strip() for s in parsed]
            logger.info("plan generated (%d subtopics): %s", len(lesson_plan), lesson_plan)
        else:
            logger.warning("plan parse failed or wrong length — using fallback. raw=%r", raw_plan)
    except Exception as exc:
        logger.error("plan LLM call failed: %s — using fallback", exc)

    # Initialise status: first subtopic is active, rest are pending
    subtopic_status = ["in_progress"] + ["pending"] * (len(lesson_plan) - 1)

    # ── LLM call 2: teach subtopic 0 ─────────────────────────────────────
    teach_prompt = build_teach_step_prompt(
        name=student_profile.get("name", "the student"),
        active_topic=active_topic,
        lesson_plan=lesson_plan,
        current_step=0,
        context_text=context_text,
        interests=", ".join(student_profile.get("interests", [])),
    )

    try:
        teaching_content = llm.invoke(teach_prompt).content.strip()
        # Guard against accidental verdict tag leak
        if "STEP_VERDICT:" in teaching_content:
            teaching_content = teaching_content.rsplit("STEP_VERDICT:", 1)[0].strip()
    except Exception as exc:
        logger.error("teach step-0 LLM call failed: %s", exc)
        plan_preview = " → ".join(f"{i + 1}. {s}" for i, s in enumerate(lesson_plan))
        teaching_content = (
            f"Alright! Here's what we'll cover about {active_topic}: {plan_preview}. "
            f"Let's start with the first one — {lesson_plan[0]}. "
            "What do you already know about this?"
        )

    return {
        "messages": [AIMessage(content=teaching_content)],
        "mode": "teacher",
        "lesson_plan": lesson_plan,
        "subtopic_status": subtopic_status,
        "current_step": 0,
        "step_context": step_context,   # topic-level context is correct for subtopic 0
        "awaiting_lesson_confirmation": False,
        "pending_topic": None,
    }


def _handle_continue(
    student_profile: dict,
    active_topic: str,
    lesson_plan: list,
    subtopic_status: list,
    current_step: int,
    step_context: list,
) -> dict:
    """
    Assess the student's response and either re-explain or advance.

    Pre-fetches the next subtopic's curriculum context from the vector DB
    before the LLM call — no extra LLM call, just a Milvus query.  This gives
    the model the next concept's material so it can teach it immediately in the
    same response when verdict == "understood", instead of producing a vague
    "let's move on" sentence.

    subtopic_status is updated and returned so the checkpointer stores accurate
    completion state.  On lesson completion the whole lesson state is cleared.
    """
    logger.info("continue: step %d/%d", current_step + 1, len(lesson_plan))

    is_last_step = current_step >= len(lesson_plan) - 1

    # Guard: if subtopic_status is missing or wrong length (e.g. old checkpointed session),
    # reconstruct a sensible default so the node doesn't crash.
    if len(subtopic_status) != len(lesson_plan):
        subtopic_status = (
            ["completed"] * current_step
            + ["in_progress"]
            + ["pending"] * max(0, len(lesson_plan) - current_step - 1)
        )

    # Pre-fetch next subtopic context before calling the LLM
    next_step = current_step + 1
    next_step_desc = ""
    next_step_context: list = []
    if not is_last_step and next_step < len(lesson_plan):
        next_step_desc = lesson_plan[next_step]
        logger.info("pre-fetching context for next subtopic: '%s'", next_step_desc)
        next_step_context = fetch_for_query(next_step_desc, student_profile)

    prompt = build_continue_prompt(
        name=student_profile.get("name", "the student"),
        active_topic=active_topic,
        lesson_plan=lesson_plan,
        subtopic_status=subtopic_status,
        current_step=current_step,
        step_context=step_context,
        interests=", ".join(student_profile.get("interests", [])),
        is_last_step=is_last_step,
        next_step_desc=next_step_desc,
        next_step_context=next_step_context,
    )

    try:
        raw = llm.invoke(prompt).content
        verdict = "understood"
        content_part = raw

        if "STEP_VERDICT:" in raw:
            content_part, verdict_part = raw.rsplit("STEP_VERDICT:", 1)
            verdict = verdict_part.strip().split()[0].lower()

        content_part = content_part.strip()
        logger.info("verdict=%s for subtopic %d ('%s')", verdict, current_step, lesson_plan[current_step])

        if verdict == "understood":
            new_status = list(subtopic_status)
            new_status[current_step] = "completed"

            if is_last_step:
                # ── Lesson complete ───────────────────────────────────────
                logger.info("lesson complete: %s", active_topic)
                return {
                    "messages": [AIMessage(content=content_part)],
                    "mode": "general",
                    "active_topic": None,
                    "lesson_plan": [],
                    "subtopic_status": [],
                    "current_step": 0,
                    "step_context": [],
                    "world_model_dirty": True,
                }
            else:
                # ── Advance to next subtopic ──────────────────────────────
                new_status[next_step] = "in_progress"
                logger.info(
                    "advancing %d→%d, status=%s", current_step, next_step, new_status
                )
                return {
                    "messages": [AIMessage(content=content_part)],
                    "current_step": next_step,
                    "step_context": next_step_context,  # fresh context for new subtopic
                    "subtopic_status": new_status,
                    "mode": "teacher",
                    "world_model_dirty": False,
                }

        else:
            # ── Stay on current subtopic ──────────────────────────────────
            return {
                "messages": [AIMessage(content=content_part)],
                "current_step": current_step,
                "step_context": step_context,
                "subtopic_status": subtopic_status,
                "mode": "teacher",
                "world_model_dirty": False,
            }

    except Exception as exc:
        logger.error("continue error: %s", exc)
        return {
            "messages": [AIMessage(content="Let me know your thoughts on that!")],
            "current_step": current_step,
            "step_context": step_context,
            "subtopic_status": subtopic_status,
            "mode": "teacher",
        }


def _handle_digress(active_topic: str, current_step: int, lesson_plan: list) -> dict:
    """Answer the off-topic question and flag that we're awaiting a yes/no to resume."""
    logger.info("digress at subtopic %d", current_step)
    prompt = build_digress_prompt(active_topic, current_step, lesson_plan)
    try:
        response = llm.invoke(prompt)
        return {"messages": [AIMessage(content=response.content)], "pending_resume": True}
    except Exception as exc:
        logger.error("digress error: %s", exc)
        return {
            "messages": [AIMessage(content=f"Got it! Want to get back to {active_topic}?")],
            "pending_resume": True,
        }


def _handle_digress_resume(active_topic: str, current_step: int, lesson_plan: list) -> dict:
    """Student confirmed resuming — bring them back to the exact subtopic position."""
    logger.info("digress_resume at subtopic %d", current_step)
    prompt = build_resume_prompt(active_topic, current_step, lesson_plan)
    try:
        response = llm.invoke(prompt)
        return {"messages": [AIMessage(content=response.content)], "pending_resume": False}
    except Exception as exc:
        logger.error("digress_resume error: %s", exc)
        return {"messages": [AIMessage(content="Great, let's pick up where we left off!")], "pending_resume": False}


def _handle_digress_exit(state: AgentState) -> dict:
    """
    Student chose not to resume — clear ALL lesson state and return to general mode.
    subtopic_status is explicitly cleared so a future learning event starts fresh.
    """
    logger.info("digress_exit")
    active_topic = state.get("active_topic", "the topic")
    lesson_plan = state.get("lesson_plan", [])
    subtopic_status = state.get("subtopic_status", [])
    current_step = state.get("current_step", 0)

    completed = sum(1 for s in subtopic_status if s == "completed")
    total = len(lesson_plan)
    msg = (
        f"No problem! We covered {completed} of {total} subtopics on {active_topic}. "
        "Feel free to ask me anything else!"
    )
    return {
        "messages": [AIMessage(content=msg)],
        "mode": "general",
        "active_topic": None,
        "lesson_plan": [],
        "subtopic_status": [],
        "current_step": 0,
        "step_context": [],
        "pending_resume": False,
        "awaiting_lesson_confirmation": False,
        "pending_topic": None,
    }
