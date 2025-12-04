# MVC Architecture Documentation

## Overview

This backend application follows the **Model-View-Controller (MVC)** architectural pattern, which separates the application into three interconnected components:

- **Models**: Data structures and database schemas
- **Views**: API routes/endpoints (presentation layer)
- **Controllers**: Business logic and data manipulation

## Project Structure

```
backend/
├── app/
│   ├── models/              # Model Layer - Data structures
│   │   ├── __init__.py
│   │   ├── user.py          # User model and schemas
│   │   ├── conversation.py  # Conversation model and schemas
│   │   └── message.py       # Message model and schemas
│   │
│   ├── controllers/         # Controller Layer - Business logic
│   │   ├── __init__.py
│   │   ├── auth_controller.py        # Authentication logic
│   │   ├── user_controller.py        # User management logic
│   │   ├── conversation_controller.py # Conversation management logic
│   │   └── message_controller.py     # Message management logic
│   │
│   ├── routers/            # View Layer - API endpoints
│   │   ├── __init__.py
│   │   ├── auth.py         # Authentication routes
│   │   ├── user.py         # User profile routes
│   │   ├── conversation.py # Conversation routes
│   │   └── message.py      # Message routes
│   │
│   ├── db_utility/         # Database utilities
│   │   ├── mongo_db.py     # MongoDB connection and schemas
│   │   ├── firestore.py    # Firestore utilities
│   │   └── vector_db.py    # Vector database utilities
│   │
│   ├── utility/            # Helper utilities
│   │   ├── security.py     # Authentication & authorization
│   │   └── firebase_init.py # Firebase initialization
│   │
│   └── main.py             # Application entry point
```

## Database Schema (ER Diagram Implementation)

### User Collection
```python
{
    "_id": str,                    # Primary key (UUID)
    "name": str,                   # User's full name
    "email": str,                  # User's email (unique)
    "password": Optional[str],     # Hashed password (for email accounts)
    "photo_url": Optional[str],    # Profile picture URL
    "grade": Optional[str],        # Student's grade/class
    "board": Optional[str],        # Education board (e.g., CBSE, ICSE)
    "personalized_response": bool, # Enable personalized AI responses
    "account_type": str,           # "email" or "google"
    "firebase_uid": Optional[str], # Firebase UID (for Google accounts)
    "created_at": datetime,        # Account creation timestamp
    "updated_at": Optional[datetime] # Last update timestamp
}
```

### Conversations Collection
```python
{
    "_id": str,           # Primary key (UUID)
    "user_id": str,       # Foreign key -> User._id
    "title": str,         # Conversation title
    "created_at": datetime, # Creation timestamp
    "updated_at": datetime  # Last update timestamp
}
```

### Messages Collection
```python
{
    "_id": str,                      # Primary key (UUID)
    "conversation_id": str,          # Foreign key -> Conversation._id
    "role": str,                     # "user" or "assistant"
    "content": str,                  # Message content
    "vector_embedding": Optional[List[float]], # For semantic search
    "created_at": datetime           # Creation timestamp
}
```

## MVC Components

### 1. Models (`app/models/`)

Models define the data structure and validation rules using Pydantic.

**Example: User Model**
```python
from app.models.user import UserCreate, UserUpdate, User, UserInDB

# UserCreate: For creating new users
# UserUpdate: For updating user information
# User: For API responses
# UserInDB: Database representation
```

### 2. Controllers (`app/controllers/`)

Controllers contain the business logic and interact with the database.

**Example: AuthController**
```python
from app.controllers.auth_controller import AuthController

auth_controller = AuthController()

# Methods:
# - register_user(user_data: UserCreate)
# - login_user(email: str, password: str)
# - google_auth(id_token: str)
```

**Key Principles:**
- Controllers handle all business logic
- Controllers interact with the database
- Controllers raise HTTPExceptions for error handling
- Controllers return dictionaries (not HTTP responses)

### 3. Views/Routes (`app/routers/`)

Routes define API endpoints and delegate to controllers.

**Example: Auth Routes**
```python
from app.routers import auth

# Endpoints:
# POST /api/v1/auth/register
# POST /api/v1/auth/login
# POST /api/v1/auth/google
```

**Key Principles:**
- Routes are thin - they only handle HTTP request/response
- Routes delegate business logic to controllers
- Routes define request/response models
- Routes handle authentication/authorization

## API Endpoints

### Authentication (`/api/v1/auth`)
- `POST /register` - Register new user
- `POST /login` - Login with email/password
- `POST /google` - Google Sign-In

### User Profile (`/api/v1/user`)
- `GET /me` - Get current user profile
- `PATCH /me` - Update current user profile
- `DELETE /me` - Delete current user account

### Conversations (`/api/v1/conversations`)
- `POST /` - Create new conversation
- `GET /` - Get all user conversations
- `GET /{conversation_id}` - Get specific conversation
- `PATCH /{conversation_id}` - Update conversation
- `DELETE /{conversation_id}` - Delete conversation

### Messages (`/api/v1/messages`)
- `POST /` - Create new message
- `GET /conversation/{conversation_id}` - Get all messages in conversation
- `GET /{message_id}` - Get specific message
- `DELETE /{message_id}` - Delete message

## Benefits of MVC Architecture

1. **Separation of Concerns**: Each layer has a specific responsibility
2. **Maintainability**: Easy to locate and fix bugs
3. **Testability**: Controllers can be tested independently
4. **Scalability**: Easy to add new features
5. **Reusability**: Controllers can be reused across different routes
6. **Code Organization**: Clear structure for large applications

## Usage Examples

### Creating a User
```python
# Model defines the structure
user_data = UserCreate(
    name="John Doe",
    email="john@example.com",
    password="securepassword",
    grade="10",
    board="CBSE",
    personalized_response=True
)

# Controller handles the logic
result = await auth_controller.register_user(user_data)

# Route returns the response
# POST /api/v1/auth/register
```

### Creating a Conversation
```python
# Model
conversation_data = ConversationCreate(title="Math Homework Help")

# Controller
result = await conversation_controller.create_conversation(
    user_id="user-uuid",
    conversation_data=conversation_data
)

# Route
# POST /api/v1/conversations
```

### Adding a Message
```python
# Model
message_data = MessageCreate(
    conversation_id="conv-uuid",
    role="user",
    content="What is the Pythagorean theorem?"
)

# Controller
result = await message_controller.create_message(
    user_id="user-uuid",
    message_data=message_data
)

# Route
# POST /api/v1/messages
```

## Authentication & Authorization

All protected endpoints require a valid JWT token:

```
Authorization: Bearer <token>
```

The `get_current_user` dependency extracts and validates the token, returning the user object.

## Error Handling

Controllers raise `HTTPException` for errors:
- `400 Bad Request` - Invalid input
- `401 Unauthorized` - Invalid credentials
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server errors

## Future Enhancements

1. Add indexes to MongoDB collections for better performance
2. Implement caching layer (Redis)
3. Add rate limiting
4. Implement websockets for real-time messaging
5. Add vector search for semantic message retrieval
6. Implement conversation summarization
7. Add message reactions and attachments
