from pymongo import MongoClient
from datetime import datetime
from app.db_utility.custom_libs import CustomMongoDBChatMessageHistory
import os
from app.db_utility.mongo_db import mongo_db





def get_chat_history(session_id: str):
    return CustomMongoDBChatMessageHistory(
        session_id=session_id,
        connection_string=os.getenv("MONGODB_CONNECTION_STRING"),
        database_name="neurosattva",
        collection_name="sessions",
        max_recent_messages=10
    )

def get_or_create_device_session_id(user_id: str):
    # return true if session id like "device_session_id_" + user_id exists in the collection
    # else create a new session id and return it
    sessions = mongo_db["sessions"]
    session_id = "device_session_id_" + user_id
    if sessions.find_one({"session_id": session_id}):
        return session_id
    else:
        sessions.insert_one({"session_id": session_id, "created_at": datetime.now()})
        return session_id