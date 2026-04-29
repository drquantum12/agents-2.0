"""
teacher_node — Socratic mentor response generator.

Dispatches to one of five sub-handlers based on sub_intent:
  new_topic       — lesson plan + teach step 1 (1 LLM call)
  continue        — assess understanding + advance step (1 LLM call)
  digress         — answer off-topic, offer to resume (1 LLM call)
  digress_resume  — bring student back to lesson (1 LLM call)
  digress_exit    — student chose not to resume; exit gracefully (no LLM)
"""

import json
import logging

from langchain_core.messages import AIMessage

from app.agents.llm import llm
from app.agents.prompts.teacher import (
    build_continue_prompt,
    build_digress_prompt,
    build_new_topic_prompt,
    build_resume_prompt,
)
from app.agents.routing import extract_json_object
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
    current_step = state.get("current_step", 0)
    step_context = state.get("step_context", [])

    logger.info(f"teacher_node: sub_intent={sub_intent}, step={current_step}/{len(lesson_plan)}")

    if sub_intent == "new_topic":
        return _handle_new_topic(student_profile, active_topic, step_context)
    if sub_intent == "continue":
        return _handle_continue(student_profile, active_topic, lesson_plan, current_step, step_context)
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

def _handle_new_topic(student_profile: dict, active_topic: str, step_context: list) -> dict:
    """
    Generate lesson plan AND teach step 1 in a single LLM call.
    Parses the structured LESSON_PLAN: [...] --- <teaching> format.
    """
    logger.info(f"new_topic: {active_topic}")

    fallback_plan = [
        f"Introduction to {active_topic}",
        f"Core concepts of {active_topic}",
        f"Applications of {active_topic}",
    ]

    prompt = build_new_topic_prompt(
        name=student_profile.get("name", "the student"),
        active_topic=active_topic,
        grade=student_profile.get("grade", 10),
        context_text="\n".join(c.get("explanation", "") for c in step_context),
        interests=", ".join(student_profile.get("interests", [])),
    )

    try:
        raw = llm.invoke(prompt).content.strip()
        lesson_plan = fallback_plan
        teaching_content = raw

        if "LESSON_PLAN:" in raw and "---" in raw:
            plan_part, _, teaching_content = raw.partition("---")
            json_str = plan_part.strip().split("LESSON_PLAN:", 1)[1].strip()
            try:
                parsed = (
                    json.loads(json_str)
                    if json_str.startswith("[")
                    else extract_json_object(json_str)
                )
                if isinstance(parsed, list) and len(parsed) >= 2:
                    lesson_plan = parsed[:5]
            except Exception:
                pass

        teaching_content = teaching_content.strip()
        # Strip any leaked STEP_VERDICT from the teaching section
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

    except Exception as exc:
        logger.error(f"new_topic error: {exc}")
        return {
            "messages": [
                AIMessage(content=f"Let's explore {active_topic}! What do you already know about it?")
            ],
            "mode": "teacher",
            "lesson_plan": fallback_plan,
            "current_step": 0,
            "awaiting_lesson_confirmation": False,
            "pending_topic": None,
        }


def _handle_continue(
    student_profile: dict,
    active_topic: str,
    lesson_plan: list,
    current_step: int,
    step_context: list,
) -> dict:
    """
    Assess understanding + advance lesson step.
    Extracts STEP_VERDICT from the LLM response to decide whether to move forward.
    """
    logger.info(f"continue: step {current_step + 1}/{len(lesson_plan)}")

    is_last_step = current_step == len(lesson_plan) - 1

    prompt = build_continue_prompt(
        name=student_profile.get("name", "the student"),
        active_topic=active_topic,
        lesson_plan=lesson_plan,
        current_step=current_step,
        step_context=step_context,
        interests=", ".join(student_profile.get("interests", [])),
        is_last_step=is_last_step,
    )

    try:
        raw = llm.invoke(prompt).content
        verdict = "understood"
        content_part = raw

        if "STEP_VERDICT:" in raw:
            content_part, verdict_part = raw.rsplit("STEP_VERDICT:", 1)
            verdict = verdict_part.strip().split()[0].lower()

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

    except Exception as exc:
        logger.error(f"continue error: {exc}")
        return {"messages": [AIMessage(content="Let me know your thoughts on that!")]}


def _handle_digress(active_topic: str, current_step: int, lesson_plan: list) -> dict:
    """Answer the off-topic question and set pending_resume=True."""
    logger.info("digress")
    prompt = build_digress_prompt(active_topic, current_step, lesson_plan)
    try:
        response = llm.invoke(prompt)
        return {"messages": [AIMessage(content=response.content)], "pending_resume": True}
    except Exception as exc:
        logger.error(f"digress error: {exc}")
        return {
            "messages": [AIMessage(content=f"Got it! Want to get back to {active_topic}?")],
            "pending_resume": True,
        }


def _handle_digress_resume(active_topic: str, current_step: int, lesson_plan: list) -> dict:
    """Student confirmed resuming — bring them back without restarting."""
    logger.info("digress_resume")
    prompt = build_resume_prompt(active_topic, current_step, lesson_plan)
    try:
        response = llm.invoke(prompt)
        return {"messages": [AIMessage(content=response.content)], "pending_resume": False}
    except Exception as exc:
        logger.error(f"digress_resume error: {exc}")
        return {"messages": [AIMessage(content="Great, let's continue!")], "pending_resume": False}


def _handle_digress_exit(state: AgentState) -> dict:
    """Student chose not to resume — exit lesson and reset to general mode."""
    logger.info("digress_exit")
    active_topic = state.get("active_topic", "the topic")
    lesson_plan = state.get("lesson_plan", [])
    current_step = state.get("current_step", 0)
    msg = (
        f"No problem! We covered {current_step + 1} of {len(lesson_plan)} steps "
        f"on {active_topic}. Feel free to ask me anything else!"
    )
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
