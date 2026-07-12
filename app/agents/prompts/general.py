"""
prompts/general.py
"""

from ..state import AgentState


def build_general_prompt(state: AgentState) -> str:
    query         = state.get("query", "")
    lesson_status = (state.get("lesson_status") or "OFF").upper()
    topic         = state.get("topic")
    messages      = state.get("messages", [])
    grade         = state.get("grade")

    recent = (
        "\n".join(f"  {m.__class__.__name__}: {m.content}" for m in messages[-4:])
        if messages else "  (none)"
    )
    grade_ctx  = f"The student is in Grade {grade}." if grade else ""
    lesson_hint = (
        f"\nNote: the student has an active lesson on '{topic}'. "
        "If it feels natural, gently suggest returning to it — but don't force it."
        if lesson_status == "ON" and topic else ""
    )

    return f"""You are a friendly, encouraging AI tutor for students. {grade_ctx}{lesson_hint}

Recent Conversation:
{recent}

Student: "{query}"

Respond warmly and helpfully. Keep it conversational and brief (2–4 sentences).
Write in plain Text-to-Speech friendly spoken sentences only. Do not use markdown, bullet points, headers,
asterisks, hashtags, numbered lists, bold, italics, URLs, or any special symbols.

Response:"""
