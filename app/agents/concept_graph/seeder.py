"""
One-time script to seed the initial CBSE/ICSE curriculum into Milvus.

Run with:  python -m app.agents.concept_graph.seeder
"""
import json
import logging
import os

from app.agents.concept_graph.schema import ConceptNode
from app.agents.concept_graph.store import upsert_meta

logger = logging.getLogger(__name__)

SEED_CONCEPTS = [
    ConceptNode(
        concept_id="physics.mechanics.force_basics",
        name="Force and its Effects",
        subject="physics",
        grade_levels=["8", "9"],
        boards=["CBSE", "ICSE", "IB"],
        prerequisite_ids=[],
        related_ids=["physics.mechanics.mass_inertia", "physics.mechanics.newtons_second_law"],
        core_explanation=(
            "A force is a push or pull on an object. Forces can change the speed, "
            "direction, or shape of an object. Force is measured in Newtons (N)."
        ),
        common_analogies=[
            {"text": "pushing a door open or closed", "effectiveness": 0.90},
            {"text": "kicking a football changes its direction", "effectiveness": 0.85},
        ],
        board_examples={
            "CBSE": "A 2 kg book rests on a table. What forces act on it?",
            "ICSE": "Describe three effects of force with everyday examples.",
        },
        socratic_questions=[
            "If you push a wall with all your strength and it doesn't move, is there a force acting?",
            "What happens to a moving ball if no force acts on it?",
        ],
        global_friction_rate=0.20,
    ),
    ConceptNode(
        concept_id="physics.mechanics.mass_inertia",
        name="Mass and Inertia",
        subject="physics",
        grade_levels=["9"],
        boards=["CBSE", "ICSE", "IB"],
        prerequisite_ids=["physics.mechanics.force_basics"],
        related_ids=["physics.mechanics.newtons_second_law"],
        core_explanation=(
            "Mass is the amount of matter in an object. Inertia is the tendency "
            "of an object to resist changes to its state of motion. Greater mass means "
            "greater inertia."
        ),
        common_analogies=[
            {"text": "a bowling ball vs a tennis ball on ice", "effectiveness": 0.88},
            {"text": "sliding a heavy sofa vs a light chair", "effectiveness": 0.82},
        ],
        board_examples={
            "CBSE": "Why is it harder to stop a truck than a bicycle moving at the same speed?",
            "ICSE": "Compare the inertia of a 5 kg stone and a 0.5 kg rubber ball.",
        },
        socratic_questions=[
            "Why do passengers lurch forward when a bus brakes suddenly?",
            "If mass increases, what happens to an object's resistance to acceleration?",
        ],
        global_friction_rate=0.35,
    ),
    ConceptNode(
        concept_id="physics.mechanics.newtons_second_law",
        name="Newton's Second Law (F=ma)",
        subject="physics",
        grade_levels=["9", "10"],
        boards=["CBSE", "ICSE", "IB"],
        prerequisite_ids=["physics.mechanics.force_basics", "physics.mechanics.mass_inertia"],
        related_ids=["physics.mechanics.momentum", "physics.mechanics.newtons_third_law"],
        core_explanation=(
            "Force equals mass times acceleration. A larger force causes greater "
            "acceleration. A heavier object requires more force for the same acceleration."
        ),
        common_analogies=[
            {"text": "pushing a loaded shopping cart vs an empty one", "effectiveness": 0.88},
            {"text": "bicycle vs truck — same engine, different speed", "effectiveness": 0.74},
        ],
        board_examples={
            "CBSE": "A 5 kg box is pushed with 20 N force. Find acceleration.",
            "ICSE": "A car of mass 1200 kg accelerates at 2 m/s². Find force.",
        },
        socratic_questions=[
            "If you push two boxes — one 2 kg and one 10 kg — with the same force, which moves faster?",
            "Why is it harder to stop a truck than a bicycle moving at the same speed?",
        ],
        global_friction_rate=0.42,
    ),
    ConceptNode(
        concept_id="chemistry.atomic_structure.atoms_and_molecules",
        name="Atoms and Molecules",
        subject="chemistry",
        grade_levels=["8", "9"],
        boards=["CBSE", "ICSE", "IB"],
        prerequisite_ids=[],
        related_ids=["chemistry.atomic_structure.electron_configuration"],
        core_explanation=(
            "An atom is the smallest unit of an element that retains its chemical "
            "properties. Molecules are formed when two or more atoms bond together."
        ),
        common_analogies=[
            {"text": "LEGO bricks — atoms are bricks, molecules are structures you build", "effectiveness": 0.92},
            {"text": "letters of the alphabet forming words", "effectiveness": 0.80},
        ],
        board_examples={
            "CBSE": "How many atoms are in one molecule of water (H2O)?",
            "ICSE": "Distinguish between an atom and a molecule with examples.",
        },
        socratic_questions=[
            "If you keep cutting a piece of gold in half, what is the smallest piece that is still gold?",
            "Why does H2O have specific properties that neither H nor O alone has?",
        ],
        global_friction_rate=0.28,
    ),
    ConceptNode(
        concept_id="maths.algebra.linear_equations",
        name="Linear Equations in One Variable",
        subject="maths",
        grade_levels=["7", "8"],
        boards=["CBSE", "ICSE", "IB"],
        prerequisite_ids=[],
        related_ids=["maths.algebra.simultaneous_equations"],
        core_explanation=(
            "A linear equation in one variable has the form ax + b = c. "
            "Solving it means finding the value of x that makes both sides equal."
        ),
        common_analogies=[
            {"text": "a balance scale — keeping both sides equal", "effectiveness": 0.95},
            {"text": "a mystery number puzzle: 'I think of a number, add 5, get 12'", "effectiveness": 0.88},
        ],
        board_examples={
            "CBSE": "Solve: 3x + 7 = 22",
            "ICSE": "A number is doubled and then increased by 5 to give 21. Find the number.",
        },
        socratic_questions=[
            "If 2x = 10, what do you need to do to both sides to find x?",
            "Why must you perform the same operation on both sides of an equation?",
        ],
        global_friction_rate=0.22,
    ),
]


def seed() -> None:
    """Insert or update all seed concepts in Milvus and MongoDB mirror."""
    import os
    from pymilvus import MilvusClient, DataType, FieldSchema, CollectionSchema
    from app.db_utility.vector_db import generate_embedding

    uri = os.getenv("MILVUS_URI")
    token = os.getenv("MILVUS_TOKEN")
    client = MilvusClient(uri=uri, token=token)
    collection_name = "concept_nodes"

    if not client.has_collection(collection_name):
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="concept_id", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="name", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="subject", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="grade_levels", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="boards", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="prerequisite_ids", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="related_ids", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="core_explanation", dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="common_analogies", dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="board_examples", dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="socratic_questions", dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="global_friction_rate", dtype=DataType.FLOAT),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=768),
        ]
        schema = CollectionSchema(fields=fields, description="Concept nodes for vijayebhav")
        client.create_collection(collection_name=collection_name, schema=schema)
        client.create_index(
            collection_name=collection_name,
            index_params=[{
                "field_name": "embedding",
                "index_type": "IVF_FLAT",
                "metric_type": "COSINE",
                "params": {"nlist": 128},
            }],
        )
        logger.info(f"Created Milvus collection: {collection_name}")

    inserted = 0
    for node in SEED_CONCEPTS:
        try:
            embedding = generate_embedding(node.name + " " + node.core_explanation)
            node.embedding = embedding
            row = {
                "concept_id": node.concept_id,
                "name": node.name,
                "subject": node.subject,
                "grade_levels": json.dumps(node.grade_levels),
                "boards": json.dumps(node.boards),
                "prerequisite_ids": json.dumps(node.prerequisite_ids),
                "related_ids": json.dumps(node.related_ids),
                "core_explanation": node.core_explanation,
                "common_analogies": json.dumps(node.common_analogies),
                "board_examples": json.dumps(node.board_examples),
                "socratic_questions": json.dumps(node.socratic_questions),
                "global_friction_rate": node.global_friction_rate,
                "embedding": node.embedding,
            }
            client.insert(collection_name=collection_name, data=[row])
            upsert_meta(node)
            inserted += 1
        except Exception as e:
            logger.error(f"Failed to seed {node.concept_id}: {e}")

    logger.info(f"Seeded {inserted}/{len(SEED_CONCEPTS)} concepts into Milvus.")
    print(f"Seeded {inserted}/{len(SEED_CONCEPTS)} concepts.")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    seed()
