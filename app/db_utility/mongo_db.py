from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from typing import TypedDict, Optional
from datetime import datetime
import os

# available collections : users, conversations

class UserSchema(TypedDict):
    _id: str
    name: str
    email: str
    photo_url: Optional[str]
    created_at: datetime

class MongoDBClient:
    """
    A class to interact with MongoDB.
    """

    def __init__(self, database_name: str):
        self.connection_string = os.getenv("MONGODB_CONNECTION_STRING")
        if not self.connection_string:
            raise ValueError("MONGODB_CONNECTION_STRING environment variable is not set.")
        self.client = MongoClient(self.connection_string)
        self.database: Database = self.client[database_name]
        # self.user_collection: Collection = self.database["users"]
        # self.session_collection: Collection = self.database["sessions"]

    def get_collection(self, collection_name: str) -> Collection:
        return self.database[collection_name]

    def close(self):
        self.client.close()

mongo_db = MongoDBClient(database_name="neurosattva").database
    