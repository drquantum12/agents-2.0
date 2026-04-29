"""
Prompt builders for teacher-mode nodes.

Each function returns a ready-to-invoke prompt string.
Keeping prompts here (separate from node logic) makes them easy to tune
without touching routing or state-management code.
"""


def build_new_topic_prompt(
    name: str,
    active_topic: str,
    grade: int,
    context_text: str,
    interests: str,
) -> str:
    """
    Combined single-call prompt: build a lesson plan AND teach step 1.
    Expected response format:
        LESSON_PLAN: ["step 1", "step 2", ...]
        ---
        <teaching content for step 1>
    """
    return (
        f'You are {name}\'s personal mentor. The student wants to learn: "{active_topic}"\n\n'
        "You have two tasks. Do BOTH in one response.\n\n"
        f"TASK 1 — Build a 3-5 step lesson plan for CBSE grade {grade} (basics to advanced).\n"
        "TASK 2 — Teach step 1 right now: explain clearly, use an analogy from their interests, "
        "end with ONE Socratic question. 3-5 sentences, conversational tone.\n\n"
        "CONCEPT CONTEXT (use as ground truth):\n"
        f"{context_text if context_text else 'Teach from general knowledge.'}\n\n"
        f"STUDENT INTERESTS (for analogies): {interests if interests else 'general topics'}\n\n"
        "Respond in EXACTLY this format — no extra text:\n"
        'LESSON_PLAN: ["step 1 desc", "step 2 desc", "step 3 desc"]\n'
        "---\n"
        "[Your teaching for step 1 here]"
    )


def build_continue_prompt(
    name: str,
    active_topic: str,
    lesson_plan: list,
    current_step: int,
    step_context: list,
    interests: str,
    is_last_step: bool,
) -> str:
    """
    Assess the student's response and continue (or close) the lesson.
    The LLM must append: STEP_VERDICT: understood | partial | not_understood
    """
    plan_text = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(lesson_plan))
    context_text = (
        "\n".join(c.get("explanation", "") for c in step_context)
        if step_context
        else "Proceed with teaching."
    )

    return (
        f'You are {name}\'s personal mentor. You\'re mid-lesson on "{active_topic}".\n\n'
        f"LESSON PLAN:\n{plan_text}\n\n"
        f"CURRENT STEP ({current_step + 1} of {len(lesson_plan)}) — IS LAST STEP: {is_last_step}:\n"
        f"{lesson_plan[current_step]}\n\n"
        f"CONCEPT CONTEXT:\n{context_text}\n\n"
        f"STUDENT INTERESTS: {interests}\n\n"
        "The student's last message was their response to your question.\n\n"
        "YOUR TASK:\n"
        "1. Assess if they understood (understood | partial | not_understood).\n"
        "2. If UNDERSTOOD and NOT last step: praise naturally, bridge to next step, end with ONE Socratic question.\n"
        "3. If UNDERSTOOD and IS LAST STEP: congratulate warmly (not over the top), "
        "recap lesson in 2-3 sentences, ask if they want a recall exercise.\n"
        "4. If PARTIAL/NOT_UNDERSTOOD: re-explain with a different analogy, ask simpler question.\n\n"
        "Keep it conversational, 3-5 sentences.\n\n"
        "At the very end, output:\n"
        "STEP_VERDICT: understood | partial | not_understood"
    )


def build_digress_prompt(active_topic: str, current_step: int, lesson_plan: list) -> str:
    """Answer the off-topic question, then gently offer to resume."""
    return (
        f'You are a mentor. You\'re in the middle of a lesson on "{active_topic}" '
        f"(step {current_step + 1} of {len(lesson_plan)}).\n"
        "The student just asked something unrelated.\n\n"
        "Answer briefly (2-4 sentences), as a knowledgeable friend would.\n\n"
        f'Then, on a new paragraph, gently ask: "Want to get back to {active_topic}?"\n'
        "Keep it light — no pressure."
    )


def build_resume_prompt(active_topic: str, current_step: int, lesson_plan: list) -> str:
    """Student confirmed resuming — bring them back without restarting."""
    return (
        f'Student confirmed they want to continue the lesson on "{active_topic}".\n'
        f'We were on step {current_step + 1}: "{lesson_plan[current_step]}"\n\n'
        "Warmly bring them back — remind them briefly where they were (one sentence), "
        "then re-ask your last Socratic question. Don't restart."
    )
