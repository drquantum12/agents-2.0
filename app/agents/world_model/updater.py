from dataclasses import dataclass, field
from typing import Optional, Tuple
from datetime import datetime

from app.agents.world_model.schema import (
    StudentWorldModel, ConceptEdge, FrictionEntry, OpenThread
)


@dataclass
class FrictionUpdate:
    concept_id: str
    analogy: str


@dataclass
class WorldModelDelta:
    """Produced by response_composer, applied by updater."""
    concept_state_updates: dict = field(default_factory=dict)
    friction_update: Optional[FrictionUpdate] = None
    new_open_thread: Optional[str] = None
    resolved_thread_ids: list = field(default_factory=list)
    curiosity_signal: Optional[str] = None
    fatigue_delta: float = 0.0
    student_analogy: Optional[Tuple[str, str]] = None  # (concept_id, analogy_text)


def apply_delta(model: StudentWorldModel, delta: WorldModelDelta) -> StudentWorldModel:
    """Mutates model in-place and saves to MongoDB."""
    from app.agents.world_model import store as wm_store

    # Lazy import to avoid circular dependency
    def _get_concept_name(concept_id: str) -> str:
        try:
            from app.agents.concept_graph import store as concept_store
            return concept_store.get_name(concept_id)
        except Exception:
            return concept_id

    # 1. Update knowledge edge states
    edge_map = {e.concept_id: e for e in model.knowledge_edges}
    for concept_id, new_state in delta.concept_state_updates.items():
        if concept_id in edge_map:
            edge_map[concept_id].state = new_state
            edge_map[concept_id].confidence = 0.8 if new_state == "known" else 0.3
        else:
            model.knowledge_edges.append(ConceptEdge(
                concept_id=concept_id,
                concept_name=_get_concept_name(concept_id),
                state=new_state,
                confidence=0.3 if new_state == "shaky" else 0.8,
            ))

    # 2. Log friction
    if delta.friction_update:
        entry = next(
            (f for f in model.friction_log if f.concept_id == delta.friction_update.concept_id),
            None,
        )
        if entry:
            entry.attempts += 1
            entry.analogies_tried.append(delta.friction_update.analogy)
        else:
            model.friction_log.append(FrictionEntry(
                concept_id=delta.friction_update.concept_id,
                attempts=1,
                analogies_tried=[delta.friction_update.analogy],
            ))

    # 3. Store student's own analogy
    if delta.student_analogy:
        cid, analogy = delta.student_analogy
        entry = next((f for f in model.friction_log if f.concept_id == cid), None)
        if entry:
            entry.student_analogy = analogy

    # 4. Open / close threads
    if delta.new_open_thread:
        model.open_threads.append(OpenThread(
            question=delta.new_open_thread,
            raised_at=datetime.utcnow(),
            concept_ids=[model.current_topic or ""],
        ))
    for tid in delta.resolved_thread_ids:
        for t in model.open_threads:
            if t.question == tid:
                t.resolved = True

    # 5. Curiosity signal
    if delta.curiosity_signal:
        if delta.curiosity_signal not in model.curiosity_topics:
            model.curiosity_topics.append(delta.curiosity_signal)

    # 6. Fatigue
    model.current_session_fatigue = min(
        1.0, max(0.0, model.current_session_fatigue + delta.fatigue_delta)
    )

    # 7. Persist
    model.updated_at = datetime.utcnow()
    wm_store.save(model)
    return model
