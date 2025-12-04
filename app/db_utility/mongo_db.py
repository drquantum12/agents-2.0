from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from typing import TypedDict, Optional, List
from datetime import datetime
import os

# Database Collections: users, conversations, messages

class UserSchema(TypedDict):
    """User collection schema"""
    _id: str
    name: str
    email: str
    password: Optional[str]  # Only for email accounts
    photo_url: Optional[str]
    grade: Optional[str]
    board: Optional[str]
    personalized_response: Optional[bool]
    account_type: str  # "email" or "google"
    firebase_uid: Optional[str]  # Only for Google accounts
    created_at: datetime
    updated_at: Optional[datetime]


class ConversationSchema(TypedDict):
    """Conversation collection schema"""
    _id: str
    user_id: str  # Reference to User._id
    topic: str
    created_at: datetime


class MessageDataSchema(TypedDict):
    content: str


class MessageSchema(TypedDict):
    type: str
    data: MessageDataSchema
    timestamp: datetime


class SessionSchema(TypedDict):
    """Session collection schema"""
    _id: str
    messages: List[MessageSchema]


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

    def get_collection(self, collection_name: str) -> Collection:
        """Get a collection from the database"""
        return self.database[collection_name]

    def close(self):
        """Close the database connection"""
        self.client.close()


# Initialize MongoDB connection
mongo_db = MongoDBClient(database_name="neurosattva").database
    