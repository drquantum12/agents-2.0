from dataclasses import dataclass, field


@dataclass
class ConceptNode:
    concept_id: str        # e.g. 'physics.mechanics.newtons_second_law'
    name: str              # e.g. "Newton's Second Law (F=ma)"
    subject: str           # 'physics' | 'chemistry' | 'maths' | ...
    grade_levels: list     # ['9', '10', '11']
    boards: list           # ['CBSE', 'ICSE', 'IB']

    # Knowledge structure
    prerequisite_ids: list = field(default_factory=list)
    related_ids: list = field(default_factory=list)

    # Explanation resources
    core_explanation: str = ""
    common_analogies: list = field(default_factory=list)
    # [{'text': 'pushing a shopping cart', 'effectiveness': 0.82}, ...]
    board_examples: dict = field(default_factory=dict)
    # {'CBSE': 'A 5kg box...', 'ICSE': '...'}
    socratic_questions: list = field(default_factory=list)

    # Population statistics
    global_friction_rate: float = 0.0  # 0.0–1.0 across all students
    embedding: list = field(default_factory=list)  # 768-dim gemini-embedding-001
