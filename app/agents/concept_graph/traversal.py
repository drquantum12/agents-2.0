from app.agents.world_model.schema import StudentWorldModel


def compute_next_concept(
    current_concept_id: str,
    target_concept_id: str,
    model: StudentWorldModel,
) -> tuple:
    """
    Returns (next_concept_id, teaching_mode).

    teaching_mode is one of:
      'prerequisite_repair' — student is missing a prerequisite
      'advance'             — proceed to next concept on path
      're_analogise'        — same concept, different metaphor
      'thread_resolve'      — surface an open thread
      'disengage'           — fatigue detected, pivot activity
      'lesson_complete'     — all path concepts known
    """
    from app.agents.concept_graph import store as concept_store

    # 0. Fatigue — overrides everything
    if model.current_session_fatigue >= 0.75:
        return (current_concept_id, "disengage")

    # 1. Repeated failure on current concept → try new analogy
    friction = next(
        (f for f in model.friction_log if f.concept_id == current_concept_id), None
    )
    if friction and friction.attempts >= 3:
        # Persistent failure → find the missing prerequisite
        node = concept_store.get(current_concept_id)
        for prereq_id in node.prerequisite_ids:
            edge = next(
                (e for e in model.knowledge_edges if e.concept_id == prereq_id), None
            )
            if not edge or edge.state in ("unseen", "shaky"):
                return (prereq_id, "prerequisite_repair")

    if friction and friction.attempts >= 2:
        return (current_concept_id, "re_analogise")

    # 2. Check if any prerequisite of CURRENT concept is still unseen/shaky
    node = concept_store.get(current_concept_id)
    for prereq_id in node.prerequisite_ids:
        edge = next(
            (e for e in model.knowledge_edges if e.concept_id == prereq_id), None
        )
        if not edge or edge.state == "unseen":
            return (prereq_id, "prerequisite_repair")

    # 3. Check for open threads to surface at a natural pause
    open_threads = [t for t in model.open_threads if not t.resolved]
    if open_threads and _is_natural_pause(model):
        return (current_concept_id, "thread_resolve")

    # 4. If current concept is known → advance along path
    edge = next(
        (e for e in model.knowledge_edges if e.concept_id == current_concept_id), None
    )
    if edge and edge.state == "known":
        pos = model.current_path_pos + 1
        while pos < len(model.current_path):
            next_id = model.current_path[pos]
            next_edge = next(
                (e for e in model.knowledge_edges if e.concept_id == next_id), None
            )
            if not next_edge or next_edge.state != "known":
                model.current_path_pos = pos
                return (next_id, "advance")
            pos += 1
        # All concepts on path are known → lesson complete
        return (current_concept_id, "lesson_complete")

    return (current_concept_id, "advance")


def _is_natural_pause(model: StudentWorldModel) -> bool:
    """True after a successful evaluation or at session start."""
    return model.last_teaching_mode == "advance" and model.consecutive_failures == 0
