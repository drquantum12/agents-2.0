"""
Prompt builders for teacher-mode nodes.

Three distinct teaching prompts map to the three phases of a lesson:

  build_plan_prompt       — LLM call 1 on new_topic: break topic into 3-5 subtopics.
                            Returns ONLY a JSON array — no teaching.

  build_teach_step_prompt — LLM call 2 on new_topic: teach subtopic 0 with context.
                            Also used if we ever need to re-introduce a step explicitly.

  build_continue_prompt   — Every subsequent student turn: assess understanding, then
                            either re-explain the current subtopic OR teach the next one
                            (next-step context is pre-fetched and included in the prompt).
"""


def build_plan_prompt(active_topic: str, grade: int, context_text: str) -> str:
    """
    Dedicated subtopic-breakdown prompt.

    Output must be ONLY a valid JSON array of 3–5 short strings — no other text.
    Each string is one teachable subtopic, ordered from foundational to advanced.
    """
    return (
        f'A grade {grade} CBSE student wants to learn: "{active_topic}"\n\n'
        "Break this topic into 3 to 5 subtopics that build progressively "
        "from basic understanding to real-world application. Rules for each subtopic:\n"
        "  • One distinct, teachable concept — not a recap of the whole topic\n"
        "  • Short descriptive phrase (not a full sentence)\n"
        "  • Ordered: foundational first, applied last\n\n"
        "CURRICULUM REFERENCE (use this to ground your subtopics):\n"
        f"{context_text if context_text else 'Use your knowledge of the CBSE curriculum.'}\n\n"
        "Return ONLY a valid JSON array of strings. "
        "No explanation, no numbering, no markdown fences.\n"
        'Example: ["What planets are and how they differ from stars", '
        '"The inner rocky planets", "The outer gas giants", '
        '"How planets form from stellar dust"]'
    )


def build_teach_step_prompt(
    name: str,
    active_topic: str,
    lesson_plan: list,
    current_step: int,
    context_text: str,
    interests: str,
) -> str:
    """
    Teach a specific subtopic.

    When current_step == 0, briefly show the student the full plan first so they
    know the roadmap, then immediately dive into subtopic 1.
    For all other steps this is only reached on digress_resume — the continue
    prompt handles normal step-to-step advancement inline.
    """
    subtopic = lesson_plan[current_step]
    total = len(lesson_plan)

    if current_step == 0:
        plan_lines = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(lesson_plan))
        preamble = (
            f"You are {name}'s mentor. They want to learn \"{active_topic}\".\n"
            f"Here is the lesson plan you've prepared:\n{plan_lines}\n\n"
            f"In one sentence, tell {name} what this lesson will cover. "
            f"Then immediately start teaching subtopic 1 of {total}: \"{subtopic}\""
        )
    else:
        completed = current_step
        preamble = (
            f"You are {name}'s mentor teaching \"{active_topic}\".\n"
            f"The student has completed {completed} of {total} subtopics.\n"
            f"Now teach subtopic {current_step + 1} of {total}: \"{subtopic}\""
        )

    return (
        f"{preamble}\n\n"
        "CURRICULUM CONTEXT FOR THIS SUBTOPIC:\n"
        f"{context_text if context_text else 'Use your general knowledge.'}\n\n"
        f"STUDENT INTERESTS (pick one analogy from here): {interests or 'general topics'}\n\n"
        f"Teach \"{subtopic}\" clearly in 3–5 sentences. "
        "Ground your explanation in the curriculum context above — do not contradict it. "
        "Use exactly one analogy drawn from the student's interests to make the concept concrete. "
        "End with ONE Socratic question that checks whether they understood this subtopic — "
        "conversational tone, not exam-style. "
        "Do NOT teach subsequent subtopics yet."
    )


def build_continue_prompt(
    name: str,
    active_topic: str,
    lesson_plan: list,
    subtopic_status: list,
    current_step: int,
    step_context: list,
    interests: str,
    is_last_step: bool,
    next_step_desc: str = "",
    next_step_context: list | None = None,
) -> str:
    """
    Assess the student's last response and respond in one of three ways:

      partial / not_understood → re-explain current subtopic with a different analogy
      understood + not last    → acknowledge briefly, then TEACH the next subtopic
                                  (next_step_context is pre-fetched and provided)
      understood + last        → wrap up the full lesson warmly

    The LLM must append on its own line at the very end:
        STEP_VERDICT: understood | partial | not_understood
    """
    # Progress display — show completed/active/pending for each subtopic
    status_icon = {"completed": "✓", "in_progress": "→", "pending": " "}
    plan_lines = []
    for i, step in enumerate(lesson_plan):
        status = subtopic_status[i] if i < len(subtopic_status) else "pending"
        icon = status_icon.get(status, " ")
        plan_lines.append(f"  {icon} {i + 1}. {step}")
    plan_text = "\n".join(plan_lines)

    current_context_text = (
        "\n".join(c.get("explanation", "") for c in step_context)
        if step_context
        else "Use your general knowledge for this subtopic."
    )

    # Include next-subtopic content only when there is a next step
    next_section = ""
    if not is_last_step and next_step_desc:
        next_ctx = "\n".join(c.get("explanation", "") for c in (next_step_context or []))
        next_section = (
            f"\nNEXT SUBTOPIC ({current_step + 2} of {len(lesson_plan)}): {next_step_desc}\n"
            + (f"NEXT SUBTOPIC CONTEXT:\n{next_ctx}\n" if next_ctx else "")
        )

    if is_last_step:
        on_understood = (
            "3. If UNDERSTOOD and this IS the last subtopic: "
            "congratulate the student genuinely (warm, not over the top). "
            "Recap all the subtopics they covered in 2–3 concise sentences. "
            "Then ask if they want a quick recall round to lock it in."
        )
    else:
        on_understood = (
            "3. If UNDERSTOOD and there IS a next subtopic: "
            "acknowledge their answer in one short sentence (no clichéd praise), "
            "then immediately start teaching the NEXT SUBTOPIC using the NEXT SUBTOPIC CONTEXT above. "
            "Explain it in 3–5 sentences with one analogy from their interests. "
            "End with ONE Socratic question about the NEXT SUBTOPIC — "
            "not about the subtopic you just completed."
        )

    return (
        f"You are {name}'s personal mentor. You are mid-lesson on \"{active_topic}\".\n\n"
        f"LESSON PROGRESS:\n{plan_text}\n\n"
        f"CURRENT SUBTOPIC ({current_step + 1} of {len(lesson_plan)}): "
        f"{lesson_plan[current_step]}\n"
        f"CURRENT SUBTOPIC CONTEXT:\n{current_context_text}\n"
        f"{next_section}\n"
        f"STUDENT INTERESTS (for analogies): {interests or 'general topics'}\n\n"
        "The student just responded to your Socratic question about the CURRENT SUBTOPIC.\n\n"
        "YOUR TASK — follow in order:\n"
        "1. Read the student's response carefully and assess their understanding.\n"
        "2. If PARTIAL or NOT UNDERSTOOD: re-explain the CURRENT SUBTOPIC using a "
        "completely different analogy from their interests. Do NOT advance. "
        "Ask a simpler version of the Socratic question.\n"
        f"{on_understood}\n\n"
        "TONE: mentor-friend, warm, not formal. No 'Great job!' clichés. "
        "Keep each response to 4–6 sentences max.\n\n"
        "At the very end of your response, on its own line:\n"
        "STEP_VERDICT: understood | partial | not_understood"
    )


def build_digress_prompt(active_topic: str, current_step: int, lesson_plan: list) -> str:
    """Answer the off-topic question, then gently offer to resume."""
    return (
        f"You are a mentor mid-lesson on \"{active_topic}\" "
        f"(subtopic {current_step + 1} of {len(lesson_plan)}).\n"
        "The student just asked something unrelated.\n\n"
        "Answer briefly in 2–4 sentences, as a knowledgeable friend would.\n\n"
        f"Then on a new paragraph, gently ask: \"Want to get back to {active_topic}?\"\n"
        "Keep it light — no pressure."
    )


def build_resume_prompt(active_topic: str, current_step: int, lesson_plan: list) -> str:
    """Student confirmed resuming — bring them back to the exact subtopic without restarting."""
    return (
        f"Student confirmed they want to continue the lesson on \"{active_topic}\".\n"
        f"They were on subtopic {current_step + 1} of {len(lesson_plan)}: "
        f"\"{lesson_plan[current_step]}\"\n\n"
        "In one sentence, remind them where they left off. "
        "Then re-ask your last Socratic question about this subtopic. "
        "Do not restart the full explanation."
    )
