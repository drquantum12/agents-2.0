"""
prompts/teacher.py
─────────────────────────────────────────────
All prompt builders used by the teacher node and user_confirmation node.
"""

from typing import List, Optional
from ..state import AgentState


# ── Helpers ───────────────────────────────────────────────────────────────────

def _grade_context(state: AgentState) -> str:
    grade = state.get("grade")
    board = state.get("board")
    if grade and board:
        return f"The student is in Grade {grade} ({board} curriculum)."
    if grade:
        return f"The student is in Grade {grade}."
    return ""


def _recent_messages(state: AgentState, n: int = 4) -> str:
    msgs = state.get("messages", [])
    if not msgs:
        return "(none)"
    return "\n".join(
        f"  {msg.__class__.__name__}: {msg.content}" for msg in msgs[-n:]
    )


# ── Prompt builders ───────────────────────────────────────────────────────────

def build_relevance_check_prompt(
    query: str,
    topic: str,
    current_subtopic: str,
) -> str:
    """
    Asks the LLM: is this query related to the active lesson topic?
    Expects a single-word answer: YES or NO.
    """
    return f"""You are a topic relevance checker for an AI tutoring system.

Active Lesson Topic   : {topic}
Current Subtopic      : {current_subtopic}

User Query: "{query}"

Is this query related to the active lesson topic or current subtopic?
Consider it related if the user is asking about any sub-concept, application,
or clarification that falls under the lesson topic — even if not exactly the
current subtopic.

Answer with ONLY "YES" or "NO".

Answer:"""


def build_topic_extract_prompt(query: str) -> str:
    """Extract the main educational topic from a free-form query."""
    return f"""Extract the main educational topic from this student query.
Output ONLY the topic name — concise, 2–5 words, title-cased.
Do not include verbs like "explain" or "what is".

Query: "{query}"

Topic:"""


def build_short_explanation_prompt(query: str, state: AgentState) -> str:
    """
    Brief (3–4 sentence) teaser explanation before a lesson offer.
    Calibrated to the student's grade if available.
    """
    gc = _grade_context(state)
    return f"""You are a friendly AI tutor. {gc}

Give a concise, engaging explanation (3–4 sentences) that answers this question.
Use simple language and one concrete example if helpful.
Write in plain Text-to-Speech friendly spoken sentences only — no markdown, bullet points, bold, asterisks,
numbered lists, or special symbols.
This is a preview, not a full lesson — keep it brief.

Question: "{query}"

Brief Explanation:"""


def build_lesson_plan_prompt(topic: str, state: AgentState) -> str:
    """Generate an ordered list of subtopics for a lesson."""
    gc = _grade_context(state)
    return f"""You are designing a structured lesson plan for an AI tutor. {gc}

Topic: {topic}

Create a numbered list of 5–8 subtopics that cover this topic progressively.
Rules:
  • Start with foundational concepts, end with advanced or applied ones.
  • Each subtopic is a short noun phrase (3–7 words).
  • No introductory or closing text — ONLY the numbered list.

Lesson Plan:"""


def build_subtopic_explanation_prompt(state: AgentState) -> str:
    """
    Explain the current subtopic in the context of the lesson.
    Advances naturally from step_context.
    """
    topic       = state.get("topic", "this topic")
    subtopic    = state.get("current_subtopic", "the next concept")
    step_ctx    = state.get("step_context") or "N/A"
    lesson_plan = state.get("lesson_plan") or []
    gc          = _grade_context(state)
    recent      = _recent_messages(state, n=4)

    plan_str = (
        "\n".join(f"  {i+1}. {s}" for i, s in enumerate(lesson_plan))
        if lesson_plan else "  N/A"
    )

    return f"""You are an expert AI tutor. {gc}

Lesson Topic   : {topic}
Current Subtopic: {subtopic}
Step Context   : {step_ctx}

Full Lesson Plan:
{plan_str}

Recent Conversation:
{recent}

Your task: Explain "{subtopic}" clearly and engagingly.
Guidelines:
  • Use plain language, real-world analogies, and one concrete example.
  • Stay focused on THIS subtopic — don't jump ahead to later ones.
  • Keep it thorough but concise (under 100 words).
  • Write in plain text-to-speech friendly spoken sentences — no markdown, bullet points, bold, asterisks, or symbols.
  • End with one gentle comprehension question to check understanding.

Explanation:"""


def build_strict_mode_prompt(state: AgentState) -> str:
    """Politely redirect the student back to the active lesson."""
    topic   = state.get("topic", "the current topic")
    subtopic = state.get("current_subtopic", "this subtopic")

    return f"""You are a focused AI tutor in STRICT lesson mode.

The student has asked an off-topic question, but the lesson policy requires
staying on:
  Topic           : {topic}
  Current Subtopic: {subtopic}

Write a short, warm, polite response that:
  1. Acknowledges the student's curiosity without dismissing them.
  2. Explains that you'd like to finish the current subtopic first.
  3. Invites them to note the question for after the lesson.

Keep the tone encouraging and upbeat. No lecturing.
Write in plain text-to-speech friendly spoken sentences only. Do not use markdown, symbols, or formatting.

Response:"""


def build_lesson_restart_offer_prompt(topic: str, state: AgentState) -> str:
    """Offer to restart or continue a previously started lesson."""
    subtopic = state.get("current_subtopic")
    gc = _grade_context(state)

    if subtopic:
        context = f"you were last working on **{subtopic}**"
    else:
        context = f"you had started a lesson on **{topic}**"

    return f"""You are an AI tutor. {gc}

The student's query is related to a topic they previously studied.
Previously, {context}.

Write a short (2–3 sentence) message:
  1. Acknowledge the connection to the previous lesson.
  2. Offer to continue or restart the lesson.
  3. Ask the student to say yes to proceed.

Response:"""


def build_lesson_intro_prompt(
    topic: str,
    first_subtopic: str,
    lesson_plan: List[str],
    state: AgentState,
) -> str:
    """
    Generates the opening message when a lesson begins.
    Shows the plan and starts explaining the first subtopic.
    """
    gc       = _grade_context(state)
    plan_str = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(lesson_plan))

    return f"""You are an enthusiastic AI tutor starting a new lesson. {gc}

Topic        : {topic}
Lesson Plan  :
{plan_str}
First Subtopic: {first_subtopic}

Write a lesson opening that:
  1. Welcomes the student and briefly frames why {topic} matters (1–2 sentences).
  2. Shows the lesson plan so they know what's ahead.
  3. Dives straight into explaining "{first_subtopic}" with clarity and an example.
  4. Ends with a simple comprehension question.

Keep the tone warm, encouraging, and energetic.
Write in plain text-to-speech friendly spoken sentences only. Do not use markdown, bullet points, numbered lists,
bold, asterisks, or any special symbols — the response will be read aloud.

Opening + First Explanation:"""
