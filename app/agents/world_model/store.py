import dataclasses
from datetime import datetime
from typing import Any

from app.db_utility.mongo_db import mongo_db
from app.agents.world_model.schema import (
    StudentWorldModel, ConceptEdge, FrictionEntry, OpenThread
)

COLLECTION = "student_world_models"


def _to_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


def _deserialise(doc: dict) -> StudentWorldModel:
    doc = dict(doc)
    doc.pop("_id", None)

    doc["knowledge_edges"] = [
        ConceptEdge(**e) for e in doc.get("knowledge_edges", [])
    ]
    doc["friction_log"] = [
        FrictionEntry(**f) for f in doc.get("friction_log", [])
    ]
    doc["open_threads"] = [
        OpenThread(**t) for t in doc.get("open_threads", [])
    ]

    if isinstance(doc.get("updated_at"), str):
        doc["updated_at"] = datetime.fromisoformat(doc["updated_at"])

    return StudentWorldModel(**doc)


def load(user_id: str) -> StudentWorldModel:
    doc = mongo_db[COLLECTION].find_one({"user_id": user_id})
    if not doc:
        return StudentWorldModel(user_id=user_id, updated_at=datetime.utcnow())
    return _deserialise(doc)


def save(model: StudentWorldModel) -> None:
    data = _to_dict(model)
    mongo_db[COLLECTION].find_one_and_update(
        {"user_id": model.user_id},
        {"$set": data},
        upsert=True,
    )
