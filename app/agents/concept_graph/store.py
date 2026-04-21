import json
import logging
import os
from typing import Optional

from app.db_utility.mongo_db import mongo_db
from app.agents.concept_graph.schema import ConceptNode

logger = logging.getLogger(__name__)

MILVUS_URI = os.getenv("MILVUS_URI")
MILVUS_TOKEN = os.getenv("MILVUS_TOKEN")
CONCEPT_NODES_COLLECTION = "concept_nodes"
META_COLLECTION = "concept_graph_meta"


def _get_milvus_client():
    from pymilvus import MilvusClient
    return MilvusClient(uri=MILVUS_URI, token=MILVUS_TOKEN)


def _collection_exists(client, name: str) -> bool:
    try:
        return client.has_collection(name)
    except Exception:
        return False


def _raw_to_node(raw: dict) -> ConceptNode:
    raw = dict(raw)
    for key in ("prerequisite_ids", "common_analogies", "board_examples",
                "related_ids", "socratic_questions", "grade_levels", "boards", "embedding"):
        val = raw.get(key)
        if isinstance(val, str):
            try:
                raw[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                raw[key] = []
    raw.pop("id", None)
    raw.pop("distance", None)
    raw.pop("score", None)
    return ConceptNode(**{k: raw[k] for k in ConceptNode.__dataclass_fields__ if k in raw})


def get(concept_id: str) -> ConceptNode:
    """Fetch concept node by ID from Milvus. Falls back to a stub if not found."""
    try:
        client = _get_milvus_client()
        if not _collection_exists(client, CONCEPT_NODES_COLLECTION):
            return _make_stub(concept_id)

        results = client.query(
            collection_name=CONCEPT_NODES_COLLECTION,
            filter=f'concept_id == "{concept_id}"',
            output_fields=["*"],
        )
        if results:
            return _raw_to_node(results[0])
    except Exception as e:
        logger.warning(f"concept_store.get({concept_id}) failed: {e}")
    return _make_stub(concept_id)


def get_name(concept_id: str) -> str:
    """Fast name lookup from MongoDB mirror."""
    try:
        doc = mongo_db[META_COLLECTION].find_one({"concept_id": concept_id})
        if doc:
            return doc["name"]
    except Exception as e:
        logger.warning(f"concept_store.get_name({concept_id}) failed: {e}")
    # Fall back to formatting the ID
    return concept_id.split(".")[-1].replace("_", " ").title()


def search_by_topic(topic: str, top_k: int = 10) -> list:
    """Semantic search for concepts relevant to a topic query."""
    try:
        from app.db_utility.vector_db import generate_embedding
        client = _get_milvus_client()
        if not _collection_exists(client, CONCEPT_NODES_COLLECTION):
            return []

        embedding = generate_embedding(topic)
        results = client.search(
            collection_name=CONCEPT_NODES_COLLECTION,
            data=[embedding],
            anns_field="embedding",
            search_params={"metric_type": "COSINE", "params": {"ef": 64}},
            limit=top_k,
            output_fields=["concept_id", "name"],
        )
        nodes = []
        for r in results[0]:
            cid = r.get("entity", {}).get("concept_id", "")
            if cid:
                nodes.append(get(cid))
        return nodes
    except Exception as e:
        logger.warning(f"concept_store.search_by_topic failed: {e}")
        return []


def upsert_meta(node: ConceptNode) -> None:
    """Keep the MongoDB mirror in sync after seeding."""
    mongo_db[META_COLLECTION].find_one_and_update(
        {"concept_id": node.concept_id},
        {"$set": {
            "concept_id": node.concept_id,
            "name": node.name,
            "subject": node.subject,
            "grade_levels": node.grade_levels,
            "boards": node.boards,
            "prerequisite_ids": node.prerequisite_ids,
            "global_friction_rate": node.global_friction_rate,
        }},
        upsert=True,
    )


def _make_stub(concept_id: str) -> ConceptNode:
    """Return a minimal stub when a concept is not yet in the graph."""
    name = concept_id.split(".")[-1].replace("_", " ").title()
    subject = concept_id.split(".")[0] if "." in concept_id else "general"
    return ConceptNode(
        concept_id=concept_id,
        name=name,
        subject=subject,
        grade_levels=["9", "10", "11", "12"],
        boards=["CBSE", "ICSE", "IB"],
        core_explanation=f"Core explanation for {name}.",
        common_analogies=[{"text": "everyday experience", "effectiveness": 0.5}],
        board_examples={"CBSE": f"Example for {name}."},
        socratic_questions=[f"How would you explain {name} in your own words?"],
        global_friction_rate=0.3,
    )
