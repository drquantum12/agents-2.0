import os
from pymongo import MongoClient
from langgraph.checkpoint.mongodb import MongoDBSaver
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.base import CheckpointTuple

DB_URI = os.getenv("DB_URI", "mongodb+srv://arjuntomar:4mzs8E9gdeLAfw8r@cluster0.w6pyfx8.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")

USER_ID   = "43f4a7cd-5fef-46e4-9541-cc3d553fa22d"
SESSION   = f"device_session_id_{USER_ID}"

client      = MongoClient(DB_URI)
# checkpointer = MongoDBSaver(client=client, db_name="neurosattva")

if __name__ == "__main__":
    db = client["neurosattva"]
    username = db["users"].find_one({"_id": USER_ID})["name"]
    print(f"User name: {username}")