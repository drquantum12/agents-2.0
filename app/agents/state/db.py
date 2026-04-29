"""
MongoDB resources shared across the agent:
  - mongo_client / mongo_db         — raw PyMongo access
  - student_memory_collection       — long-term student profiles
  - checkpointer                    — LangGraph turn-state persistence (30-day TTL)
"""

import logging
import os

from langgraph.checkpoint.mongodb import MongoDBSaver
from pymongo import MongoClient

logger = logging.getLogger(__name__)

# PyMongo client is safe at module level — it doesn't connect until the first
# actual network operation, so importing this module doesn't block startup.
mongo_client = MongoClient(os.getenv("MONGODB_CONNECTION_STRING"))
mongo_db = mongo_client["neurosattva"]
student_memory_collection = mongo_db["student_memory"]
student_profile = mongo_db["users"]

# MongoDBSaver.__init__ calls list_indexes() immediately, which requires a
# live connection.  We therefore build it lazily on first use.
_checkpointer = None


def get_checkpointer() -> MongoDBSaver:
    """Return the MongoDBSaver singleton, creating it on first call."""
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = MongoDBSaver(
            client=mongo_client,
            db_name="neurosattva",
            ttl=60 * 60 * 24 * 30,  # 30 days
        )
    return _checkpointer
