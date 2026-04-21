from app.agents.world_model.schema import StudentWorldModel


def summarise_for_prompt(model: StudentWorldModel) -> str:
    """
    Returns a ≤5 sentence natural-language summary of the student's current state.
    Injected into every agent prompt as {world_model_summary}.
    """
    parts = []

    shaky = [e.concept_name for e in model.knowledge_edges if e.state == "shaky"][:3]
    if shaky:
        parts.append(f"Concepts still shaky: {', '.join(shaky)}.")

    blocked = [f for f in model.friction_log if f.attempts >= 2]
    if blocked:
        b = blocked[0]
        analogy_list = ", ".join(b.analogies_tried[:2]) if b.analogies_tried else "none yet"
        student_note = (
            f" Student's own analogy: '{b.student_analogy}'."
            if b.student_analogy
            else " No student analogy yet."
        )
        parts.append(
            f"{b.concept_id} has been attempted {b.attempts}x. "
            f"Analogies tried: {analogy_list}.{student_note}"
        )

    if model.curiosity_topics:
        parts.append(
            f"Student keeps returning to: {model.curiosity_topics[0]}. "
            "Use this as a motivating hook when possible."
        )

    open_threads = [t for t in model.open_threads if not t.resolved]
    if open_threads:
        parts.append(f"Unresolved question from student: '{open_threads[0].question}'")

    if model.current_session_fatigue > 0.6:
        parts.append("Fatigue signal detected. Keep this response short and light.")

    return " ".join(parts) if parts else "No prior learning context yet."
