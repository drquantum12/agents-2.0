"""
intent_router — first node in the LangGraph graph, runs every turn.

Priority order:
  1. Teacher + pending_resume     → digress_resume / digress_exit          (no LLM)
  2. General + awaiting_lesson_confirmation → new_topic / general          (no LLM)
  3. General + implicit yes after lesson offer                              (no LLM)
  4. Stop detection (any mode)                                              (no LLM)
  5. Unified LLM classifier — distinguishes general_chat / learning_intent
     / lesson_continue / lesson_digress / lesson_stop via structured output (1 LLM call)
     Fallback tier 1: raw JSON parsing
     Fallback tier 2: mode-based safe default
"""

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.prompts.classifier import build_classifier_prompt
from app.agents.routing import (
    LESSON_OFFER_MARKERS,
    extract_json_object,
    extract_topic_from_text,
    is_no,
    is_stop,
    is_yes,
)
from app.agents.routing.intent_schema import IntentClassification
from app.agents.state.schema import AgentState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid intent literals expected from the LLM
# ---------------------------------------------------------------------------
_VALID_INTENTS = frozenset(IntentClassification.model_fields["intent"].annotation.__args__)


def _default_classification(mode: str) -> IntentClassification:
    """Safe fallback when every tier of parsing has failed."""
    if mode == "teacher":
        return IntentClassification(intent="lesson_continue")
    return IntentClassification(intent="general_chat")


def _parse_raw_fallback(raw: str, mode: str) -> IntentClassification:
    """Tier-2 fallback: extract intent/topic from an unstructured LLM text response."""
    try:
        obj = extract_json_object(raw)
        if obj:
            intent = obj.get("intent", "")
            if intent in _VALID_INTENTS:
                return IntentClassification(intent=intent, topic=obj.get("topic", ""))  # type: ignore[arg-type]
    except Exception:
        pass
    return _default_classification(mode)


def _classify(
    mode: str,
    active_topic: str,
    user_input: str,
    awaiting_confirmation: bool = False,
) -> IntentClassification:
    """
    Call the LLM classifier with a 3-tier fallback:
      Tier 1  — ``with_structured_output`` (function-calling, fully typed)
      Tier 2  — raw ``invoke`` + JSON extraction from response text
      Tier 3  — mode-based safe default

    awaiting_confirmation=True injects extra context so the model knows the
    student is responding to a lesson offer, making "yes please" / "sure" etc.
    classify correctly as learning_intent rather than general_chat.
    """
    # Lazy import to avoid circular imports at module load time
    from app.agents.llm import fast_llm  # noqa: PLC0415

    prompt = build_classifier_prompt(mode, active_topic, user_input, awaiting_confirmation)

    # --- Tier 1: structured output ----------------------------------------
    try:
        chain = fast_llm.with_structured_output(IntentClassification)
        result = chain.invoke(prompt)
        if isinstance(result, IntentClassification):
            return result
        # Unexpected type — fall through
        logger.warning("with_structured_output returned unexpected type %s", type(result))
    except Exception as exc:
        logger.warning("Structured-output classifier failed: %s", exc)

    # --- Tier 2: raw response + JSON extraction ----------------------------
    try:
        raw_response = fast_llm.invoke(prompt)
        return _parse_raw_fallback(raw_response.content, mode)
    except Exception as exc:
        logger.warning("Raw-response classifier failed: %s", exc)

    # --- Tier 3: safe default ----------------------------------------------
    logger.warning("All classifier tiers failed — using safe default for mode=%s", mode)
    return _default_classification(mode)


def intent_router(state: AgentState) -> dict:
    """Classify user intent and set route / sub_intent for downstream nodes."""
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

    logger.info(
        "intent_router: mode=%s, pending_resume=%s, input='%.50s'",
        mode,
        pending_resume,
        user_input,
    )

    # ------------------------------------------------------------------
    # 1. Teacher + pending digression resume
    # ------------------------------------------------------------------
    if mode == "teacher" and pending_resume:
        if is_yes(user_input):
            logger.info("User confirmed resuming lesson")
            return {"route": "teacher", "sub_intent": "digress_resume", "pending_resume": False}
        if is_no(user_input):
            logger.info("User declined resuming lesson")
            return {"route": "stop_teacher", "sub_intent": "digress_exit", "pending_resume": False}

    # ------------------------------------------------------------------
    # 2. General + awaiting explicit lesson confirmation
    # ------------------------------------------------------------------
    if mode == "general" and awaiting_lesson_confirmation:
        user_lower = user_input.strip().lower()
        # is_yes handles strict patterns; the startswith check catches "yes explain
        # me in detail", "yes tell me more", "yes do it" etc. — any message that
        # opens with "yes " (yes + space) is an unambiguous confirmation.
        is_affirmative = is_yes(user_input) or user_lower.startswith("yes ")
        if is_affirmative:
            chosen_topic = pending_topic or active_topic or "this topic"
            logger.info("User confirmed lesson for topic: %s", chosen_topic)
            return {
                "route": "teacher",
                "sub_intent": "new_topic",
                "active_topic": chosen_topic,
                "awaiting_lesson_confirmation": False,
                "pending_topic": None,
            }
        if is_no(user_input):
            logger.info("User declined lesson offer")
            return {
                "route": "general",
                "sub_intent": "",
                "awaiting_lesson_confirmation": False,
                "pending_topic": None,
            }

    # ------------------------------------------------------------------
    # 3. General + implicit yes (previous AI turn offered a lesson)
    # ------------------------------------------------------------------
    if mode == "general" and is_yes(user_input):
        prev_ai = [m for m in messages[:-1] if isinstance(m, AIMessage)]
        last_ai_content = prev_ai[-1].content.lower() if prev_ai else ""
        if any(marker in last_ai_content for marker in LESSON_OFFER_MARKERS):
            inferred_topic = pending_topic or active_topic_text or "this topic"
            logger.info("Implicit lesson confirmation, topic=%s", inferred_topic)
            return {
                "route": "teacher",
                "sub_intent": "new_topic",
                "active_topic": inferred_topic,
                "awaiting_lesson_confirmation": False,
                "pending_topic": None,
            }

    # ------------------------------------------------------------------
    # 4. Stop detection (any mode)
    # ------------------------------------------------------------------
    if is_stop(user_input):
        logger.info("Stop intent detected")
        return {"route": "stop_teacher", "sub_intent": ""}

    # ------------------------------------------------------------------
    # 5. Unified LLM classifier (general AND teacher mode)
    #    Covers: general_chat / learning_intent / lesson_continue /
    #            lesson_digress / lesson_stop
    # ------------------------------------------------------------------
    result = _classify(
        mode, active_topic_text, user_input,
        awaiting_confirmation=awaiting_lesson_confirmation,
    )
    intent = result.intent
    # Use LLM-extracted topic; fall back to regex heuristic if empty
    topic = result.topic.strip() or extract_topic_from_text(user_input)

    logger.info("LLM classifier intent=%s, topic='%s'", intent, topic)

    if intent == "learning_intent":
        # Same topic while in a lesson → treat as continuing the lesson
        if mode == "teacher" and active_topic_text and topic.lower() == active_topic_text.lower():
            return {"route": "teacher", "sub_intent": "continue"}
        # Different topic while in a lesson, or any topic in teacher mode → start lesson immediately
        if mode == "teacher":
            return {
                "route": "teacher",
                "sub_intent": "new_topic",
                "active_topic": topic,
                "awaiting_lesson_confirmation": False,
                "pending_topic": None,
            }
        # General mode: check if we're already waiting for confirmation.
        if awaiting_lesson_confirmation:
            # The LLM (given the awaiting context) still classified as learning_intent —
            # the student is accepting the lesson offer even if phrased unusually
            # ("yes explain me in detail", "go ahead and teach", etc.).
            chosen_topic = pending_topic or topic or active_topic_text or "this topic"
            logger.info("Lesson confirmed via classifier for topic: %s", chosen_topic)
            return {
                "route": "teacher",
                "sub_intent": "new_topic",
                "active_topic": chosen_topic,
                "awaiting_lesson_confirmation": False,
                "pending_topic": None,
            }
        # First learning mention in general mode — offer the lesson, don't jump in.
        logger.info("General mode learning_intent — offering lesson on topic='%s'", topic)
        return {
            "route": "general",
            "sub_intent": "",
            "awaiting_lesson_confirmation": True,
            "pending_topic": topic,
            "active_topic": topic,
        }

    if intent == "lesson_digress":
        return {"route": "teacher", "sub_intent": "digress"}

    if intent == "lesson_stop":
        return {"route": "stop_teacher", "sub_intent": ""}

    if intent == "lesson_continue":
        return {"route": "teacher", "sub_intent": "continue"}

    # general_chat (or any unrecognised value — defensive)
    return {
        "route": "general",
        "sub_intent": "",
        "awaiting_lesson_confirmation": False,
    }

