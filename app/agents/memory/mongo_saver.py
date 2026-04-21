import os
from pymongo import MongoClient
from langgraph.checkpoint.mongodb import MongoDBSaver

_saver = None


def get_mongo_saver() -> MongoDBSaver:
    """Return a singleton MongoDBSaver for LangGraph checkpointing."""
    global _saver
    if _saver is None:
        _saver = MongoDBSaver(
            client=MongoClient(os.getenv("MONGODB_CONNECTION_STRING")),
            db_name="neurosattva",
        )
    return _saver
