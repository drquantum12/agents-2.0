import os
from pymongo import MongoClient
from langgraph.checkpoint.mongodb import MongoDBSaver

_saver = None

def get_mongo_saver():
    """Return a singleton MongoDBSaver for langgraph checkpointing."""
    global _saver
    if _saver is None:
        mongo_uri = os.getenv("MONGODB_CONNECTION_STRING", "mongodb://localhost:27017")
        client = MongoClient(mongo_uri)
        _saver = MongoDBSaver(client)
    return _saver