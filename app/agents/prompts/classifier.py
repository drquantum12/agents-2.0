"""
Classifier prompt for the intent_router LLM call.

Covers both general mode (distinguishing general_chat from learning_intent)
and teacher mode (lesson_continue / digress / stop / new learning_intent).

Used with ``fast_llm.with_structured_output(IntentClassification)`` — the
Pydantic schema guides the model via function-calling, so no explicit JSON
format instruction is required in the prompt itself.
"""


def build_classifier_prompt(
    mode: str,
    active_topic: str,
    user_input: str,
    awaiting_confirmation: bool = False,
) -> str:
    """Return the instructional context string for the intent classifier.

    Parameters
    ----------
    mode                  : ``"general"`` | ``"teacher"``
    active_topic          : current lesson topic, or empty string if none
    user_input            : the student's latest message
    awaiting_confirmation : True when the agent just offered a lesson and is
                            waiting for the student to accept or decline.
                            Gives the model critical context so short affirmatives
                            like "yes please" or "sure" are classified correctly.
    """
    topic_line = (
        f'Active lesson topic: "{active_topic}"'
        if active_topic
        else "No active lesson in progress."
    )

    if awaiting_confirmation and active_topic:
        mode_guidance = (
            f"IMPORTANT CONTEXT: The agent just offered to teach the student about "
            f"\"{active_topic}\" and is waiting for their response. "
            "If the student's message is at all affirmative — including short phrases like "
            "\"yes please\", \"sure\", \"ok\", \"go ahead\", \"why not\", \"sounds good\" — "
            f"classify it as 'learning_intent' with topic=\"{active_topic}\". "
            "Only classify as 'general_chat' if the student is clearly ignoring the offer "
            "or changing the subject entirely. "
            "Classify as 'lesson_stop' only if they explicitly decline (\"no\", \"not now\", etc.)."
        )
    elif mode == "general":
        mode_guidance = (
            "The student is currently in free-chat / companion mode (no active lesson)."
        )
    else:
        mode_guidance = (
            "The student is currently in the middle of an active lesson."
        )

    return (
        "You are classifying a student's message for an AI tutoring system.\n\n"
        f"Mode: {mode}\n"
        f"{topic_line}\n"
        f"{mode_guidance}\n\n"
        f'Student message: "{user_input}"\n\n'
        "Classify the student's intent. "
        "If the intent is 'learning_intent', also extract the exact topic they want to learn."
    )
