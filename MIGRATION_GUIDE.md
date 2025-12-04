# Migration Guide: Converting to MVC Architecture

## Overview

This guide explains the changes made to convert the backend from a basic structure to a proper **Model-View-Controller (MVC)** architecture.

## What Changed?

### Before (Old Structure)
```
app/
├── routers/
│   ├── auth.py      # Routes + Business Logic mixed
│   └── user.py      # Routes + Business Logic mixed
├── db_utility/
│   └── mongo_db.py  # Basic schema
└── main.py
```

### After (MVC Structure)
```
app/
├── models/          # NEW: Data structures
│   ├── user.py
│   ├── conversation.py
│   └── message.py
├── controllers/     # NEW: Business logic
│   ├── auth_controller.py
│   ├── user_controller.py
│   ├── conversation_controller.py
│   └── message_controller.py
├── routers/         # UPDATED: Thin routes
│   ├── auth.py
│   ├── user.py
│   ├── conversation.py  # NEW
│   └── message.py       # NEW
├── db_utility/
│   ├── mongo_db.py  # UPDATED: Complete schemas
│   └── init_db.py   # NEW: Database initialization
└── main.py          # UPDATED: Added new routers
```

## Database Schema Changes

### User Collection - New Fields Added

**Old Schema:**
```python
{
    "_id": str,
    "name": str,
    "email": str,
    "password": str,
    "photo_url": str,
    "account_type": str,
    "created_at": datetime
}
```

**New Schema (from ER Diagram):**
```python
{
    "_id": str,
    "name": str,
    "email": str,
    "password": Optional[str],
    "photo_url": Optional[str],
    "grade": Optional[str],              # NEW
    "board": Optional[str],              # NEW
    "personalized_response": bool,       # NEW
    "account_type": str,
    "firebase_uid": Optional[str],
    "created_at": datetime,
    "updated_at": Optional[datetime]     # NEW
}
```

### New Collections

**Conversations Collection:**
```python
{
    "_id": str,
    "user_id": str,        # References User._id
    "title": str,
    "created_at": datetime,
    "updated_at": datetime
}
```

**Messages Collection:**
```python
{
    "_id": str,
    "conversation_id": str,  # References Conversation._id
    "role": str,             # "user" or "assistant"
    "content": str,
    "vector_embedding": Optional[List[float]],
    "created_at": datetime
}
```

## Migration Steps

### Step 1: Update Environment Variables

No changes needed - existing environment variables remain the same:
- `MONGODB_CONNECTION_STRING`
- `SECRET_KEY`
- `SARVAM_API_KEY`

### Step 2: Initialize Database Indexes

Run the database initialization script to create indexes:

```bash
cd /Users/drquantum/Desktop/AI/vijayebhav_v2/backend
python -m app.db_utility.init_db
```

This will create indexes for:
- User email (unique)
- User firebase_uid
- Conversation user_id
- Message conversation_id

### Step 3: Update Existing User Documents (Optional)

If you have existing users in the database, you may want to add the new fields:

```python
from app.db_utility.mongo_db import mongo_db

# Add new fields to existing users
mongo_db["users"].update_many(
    {},
    {
        "$set": {
            "grade": None,
            "board": None,
            "personalized_response": False
        }
    }
)
```

### Step 4: Test the API

The API endpoints remain backward compatible. Test existing endpoints:

```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test User",
    "email": "test@example.com",
    "password": "password123",
    "grade": "10",
    "board": "CBSE",
    "personalized_response": true
  }'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123"
  }'

# Get Profile
curl -X GET http://localhost:8000/api/v1/user/me \
  -H "Authorization: Bearer <token>"

# Update Profile
curl -X PATCH http://localhost:8000/api/v1/user/me \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Name",
    "grade": "11",
    "personalized_response": true
  }'
```

### Step 5: Test New Endpoints

Test the new conversation and message endpoints:

```bash
# Create Conversation
curl -X POST http://localhost:8000/api/v1/conversations \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Math Homework Help"
  }'

# Get Conversations
curl -X GET http://localhost:8000/api/v1/conversations \
  -H "Authorization: Bearer <token>"

# Create Message
curl -X POST http://localhost:8000/api/v1/messages \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": "<conversation_id>",
    "role": "user",
    "content": "What is the Pythagorean theorem?"
  }'

# Get Messages
curl -X GET http://localhost:8000/api/v1/messages/conversation/<conversation_id> \
  -H "Authorization: Bearer <token>"
```

## Code Changes Breakdown

### 1. Models Layer (NEW)

**Purpose:** Define data structures and validation

**Files:**
- `app/models/user.py` - User data models
- `app/models/conversation.py` - Conversation data models
- `app/models/message.py` - Message data models

**Benefits:**
- Centralized data validation
- Type safety with Pydantic
- Reusable across controllers and routes

### 2. Controllers Layer (NEW)

**Purpose:** Business logic and database operations

**Files:**
- `app/controllers/auth_controller.py` - Authentication logic
- `app/controllers/user_controller.py` - User management
- `app/controllers/conversation_controller.py` - Conversation management
- `app/controllers/message_controller.py` - Message management

**Benefits:**
- Separation of concerns
- Testable business logic
- Reusable across different routes

### 3. Routes Layer (UPDATED)

**Purpose:** HTTP request/response handling

**Changes:**
- Routes now delegate to controllers
- Removed business logic from routes
- Added new conversation and message routes

**Benefits:**
- Thin routes (easier to read)
- Consistent error handling
- Clear API structure

## Backward Compatibility

✅ **Existing endpoints remain unchanged:**
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/google`
- `GET /api/v1/user/me`
- `PATCH /api/v1/user/me`

✅ **New optional fields:**
- `grade`, `board`, `personalized_response` are optional
- Existing users work without these fields

✅ **Response format unchanged:**
- API responses maintain the same structure

## New Features

✨ **Conversation Management:**
- Create, read, update, delete conversations
- List all user conversations
- Pagination support

✨ **Message Management:**
- Create messages in conversations
- Retrieve conversation history
- Support for vector embeddings (for future semantic search)

✨ **Enhanced User Profile:**
- Grade and board information
- Personalized response settings
- Profile deletion

## Performance Improvements

🚀 **Database Indexes:**
- Faster user lookups by email
- Optimized conversation queries by user_id
- Efficient message retrieval by conversation_id

🚀 **Query Optimization:**
- Pagination on list endpoints
- Sorted results (newest first)
- Efficient cascade deletes

## Testing Checklist

- [ ] Existing users can still login
- [ ] New users can register with additional fields
- [ ] Google Sign-In still works
- [ ] User profile updates work
- [ ] Conversations can be created
- [ ] Messages can be added to conversations
- [ ] Pagination works on list endpoints
- [ ] Authorization prevents unauthorized access
- [ ] Cascade deletes work (deleting conversation deletes messages)

## Rollback Plan

If you need to rollback:

1. The old code is preserved in git history
2. New collections (conversations, messages) can be dropped
3. New user fields can be removed with:
   ```python
   mongo_db["users"].update_many(
       {},
       {"$unset": {"grade": "", "board": "", "personalized_response": ""}}
   )
   ```

## Support

For issues or questions:
1. Check `MVC_ARCHITECTURE.md` for architecture details
2. Review controller code for business logic
3. Check model definitions for data structures
4. Review route files for API endpoints

## Next Steps

1. ✅ Database initialization
2. ✅ Test existing endpoints
3. ✅ Test new endpoints
4. 🔲 Add integration tests
5. 🔲 Add API documentation (Swagger/OpenAPI)
6. 🔲 Implement vector search for messages
7. 🔲 Add conversation summarization
8. 🔲 Implement real-time messaging (WebSockets)
