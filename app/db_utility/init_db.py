"""
Database initialization script for MongoDB collections.
Creates indexes for better query performance.
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
import os


def initialize_database():
    """Initialize MongoDB database with collections and indexes"""
    
    connection_string = os.getenv("MONGODB_CONNECTION_STRING")
    if not connection_string:
        raise ValueError("MONGODB_CONNECTION_STRING environment variable is not set.")
    
    client = MongoClient(connection_string)
    db = client["neurosattva"]
    
    print("Initializing database collections and indexes...")
    
    # ===== USERS COLLECTION =====
    users_collection = db["users"]
    
    # Create indexes for users
    users_collection.create_index([("email", ASCENDING)], unique=True)
    users_collection.create_index([("firebase_uid", ASCENDING)], sparse=True)
    users_collection.create_index([("created_at", DESCENDING)])
    
    print("✓ Users collection indexes created")
    
    # ===== CONVERSATIONS COLLECTION =====
    conversations_collection = db["conversations"]
    
    # Create indexes for conversations
    conversations_collection.create_index([("user_id", ASCENDING)])
    conversations_collection.create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)])
    conversations_collection.create_index([("created_at", DESCENDING)])
    
    print("✓ Conversations collection indexes created")
    
    # ===== MESSAGES COLLECTION =====
    messages_collection = db["messages"]
    
    # Create indexes for messages
    messages_collection.create_index([("conversation_id", ASCENDING)])
    messages_collection.create_index([("conversation_id", ASCENDING), ("created_at", ASCENDING)])
    messages_collection.create_index([("created_at", DESCENDING)])
    
    print("✓ Messages collection indexes created")
    
    # Print collection statistics
    print("\n" + "="*50)
    print("Database Statistics:")
    print("="*50)
    
    for collection_name in ["users", "conversations", "messages"]:
        collection = db[collection_name]
        count = collection.count_documents({})
        indexes = list(collection.list_indexes())
        
        print(f"\n{collection_name.upper()}:")
        print(f"  Documents: {count}")
        print(f"  Indexes: {len(indexes)}")
        for idx in indexes:
            print(f"    - {idx['name']}")
    
    print("\n" + "="*50)
    print("Database initialization complete!")
    print("="*50)
    
    client.close()


if __name__ == "__main__":
    initialize_database()
