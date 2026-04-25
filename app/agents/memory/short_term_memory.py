import os
from pymongo import MongoClient
from langgraph.checkpoint.mongodb import MongoDBSaver

_saver = None

_CHECKPOINT_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days


def get_mongo_saver():
    """Return a singleton MongoDBSaver with a 7-day TTL on checkpoint documents."""
    global _saver
    if _saver is None:
        mongo_uri = os.getenv("MONGODB_CONNECTION_STRING", "mongodb://localhost:27017")
        client = MongoClient(mongo_uri)
        _saver = MongoDBSaver(
            client,
            ttl=_CHECKPOINT_TTL_SECONDS,
        )
    return _saver