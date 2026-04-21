from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class ConceptEdge:
    concept_id: str
    concept_name: str
    state: str  # 'known' | 'shaky' | 'unseen' | 'blocked'
    confidence: float  # 0.0–1.0
    last_visited: Optional[datetime] = None


@dataclass
class FrictionEntry:
    concept_id: str
    attempts: int
    analogies_tried: list
    analogy_that_worked: Optional[str] = None
    student_analogy: Optional[str] = None


@dataclass
class OpenThread:
    question: str
    raised_at: datetime
    concept_ids: list
    resolved: bool = False


@dataclass
class StudentWorldModel:
    user_id: str
    updated_at: datetime

    # One edge per concept the student has ever encountered.
    # State transitions: unseen → shaky → known (or → blocked)
    knowledge_edges: list = field(default_factory=list)

    # Keyed by concept_id. Updated when evaluation fails.
    friction_log: list = field(default_factory=list)

    # Topics the student keeps returning to unprompted.
    curiosity_topics: list = field(default_factory=list)

    # domain → avg concepts mastered per session
    velocity_per_domain: dict = field(default_factory=dict)

    # 0.0 = fresh, 1.0 = cognitive overload signal detected
    current_session_fatigue: float = 0.0

    # Questions raised but not yet fully answered.
    open_threads: list = field(default_factory=list)

    current_topic: Optional[str] = None
    current_path: list = field(default_factory=list)
    current_path_pos: int = 0
    last_teaching_mode: Optional[str] = None
    consecutive_failures: int = 0
