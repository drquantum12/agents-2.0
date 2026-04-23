from dataclasses import dataclass, field


@dataclass
class ConceptNode:
    board: str
    class_name: str
    subject: str
    chapter: str
    concept: str
    explanation: str
    analogies: str
    embedding: list[float] = field(default_factory=list)
