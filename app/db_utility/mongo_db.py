from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from typing import TypedDict, Optional, List
from datetime import datetime
import os

# Existing collections: users, conversations, messages, sessions, device_config, devices, notifications
# Reimagined agent collections (auto-created on first write, no migration needed):
#   student_world_models — one document per user; the persistent Student World Model
#   concept_graph_meta   — lightweight MongoDB mirror of Milvus concept nodes for fast name lookups

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

class DeviceConfigurationSchema(TypedDict):
    """Device configuration collection schema"""
    _id: str
    user_id: str  # Reference to User._id
    learning_mode: str  # Strict / Normal
    response_type: str  # Detailed / Concise
    difficulty_level: str  # Beginner / Intermediate / Advanced


class StudentWorldModelSchema(TypedDict):
    """
    student_world_models collection — reimagined agent.
    One document per user. Updated after every turn.
    Unique index on user_id.
    """
    user_id: str
    updated_at: datetime
    knowledge_edges: List[dict]    # [{'concept_id', 'concept_name', 'state', 'confidence'}]
    friction_log: List[dict]       # [{'concept_id', 'attempts', 'analogies_tried', ...}]
    curiosity_topics: List[str]
    velocity_per_domain: dict      # {'physics': 1.8, 'chemistry': 0.9}
    current_session_fatigue: float  # 0.0–1.0
    open_threads: List[dict]       # [{'question', 'raised_at', 'concept_ids', 'resolved'}]
    current_topic: Optional[str]
    current_path: List[str]        # ordered concept_ids for current lesson
    current_path_pos: int
    last_teaching_mode: Optional[str]
    consecutive_failures: int


class ConceptGraphMetaSchema(TypedDict):
    """
    concept_graph_meta collection — reimagined agent.
    Lightweight MongoDB mirror of Milvus concept nodes.
    Unique index on concept_id.
    Used for fast name lookups without hitting Milvus.
    """
    concept_id: str
    name: str
    subject: str
    grade_levels: List[str]
    boards: List[str]
    prerequisite_ids: List[str]
    global_friction_rate: float


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
    