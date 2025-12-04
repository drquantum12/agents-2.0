# Backend Application - MVC Structure

This directory contains the backend application organized using the **Model-View-Controller (MVC)** architectural pattern.

## Directory Structure

```
app/
├── models/              # MODEL LAYER - Data structures and validation
│   ├── __init__.py
│   ├── user.py          # User models (UserCreate, UserUpdate, User, UserInDB)
│   ├── conversation.py  # Conversation models
│   └── message.py       # Message models
│
├── controllers/         # CONTROLLER LAYER - Business logic
│   ├── __init__.py
│   ├── auth_controller.py        # Authentication logic
│   ├── user_controller.py        # User profile management
│   ├── conversation_controller.py # Conversation CRUD operations
│   └── message_controller.py     # Message CRUD operations
│
├── routers/            # VIEW LAYER - API endpoints (HTTP handling)
│   ├── __init__.py
│   ├── auth.py         # Authentication routes
│   ├── user.py         # User profile routes
│   ├── conversation.py # Conversation routes
│   └── message.py      # Message routes
│
├── db_utility/         # Database utilities
│   ├── __init__.py
│   ├── mongo_db.py     # MongoDB connection and schemas
│   ├── init_db.py      # Database initialization script
│   ├── firestore.py    # Firestore utilities
│   └── vector_db.py    # Vector database utilities
│
├── utility/            # Helper utilities
│   ├── security.py     # JWT, password hashing, authentication
│   └── firebase_init.py # Firebase Admin SDK initialization
│
├── data/               # Data files (audio, etc.)
├── prompts.py          # AI prompt templates
└── main.py             # Application entry point
```

## Layer Responsibilities

### 📊 Models Layer (`models/`)

**Purpose:** Define data structures, validation rules, and type safety

**What it does:**
- Defines Pydantic models for request/response validation
- Ensures type safety across the application
- Provides clear data contracts

**Example:**
```python
from app.models.user import UserCreate

user = UserCreate(
    name="John Doe",
    email="john@example.com",
    password="secure123"
)
```

**Files:**
- `user.py` - User-related models (UserCreate, UserUpdate, User, UserInDB)
- `conversation.py` - Conversation models
- `message.py` - Message models

### 🎮 Controllers Layer (`controllers/`)

**Purpose:** Implement business logic and database operations

**What it does:**
- Processes business rules
- Interacts with the database
- Handles data transformation
- Raises HTTPExceptions for errors
- Returns plain dictionaries (not HTTP responses)

**Example:**
```python
from app.controllers.auth_controller import AuthController

auth_controller = AuthController()
result = await auth_controller.register_user(user_data)
```

**Files:**
- `auth_controller.py` - User registration, login, Google auth
- `user_controller.py` - Profile get/update/delete
- `conversation_controller.py` - Conversation CRUD
- `message_controller.py` - Message CRUD

### 🌐 Routes/Views Layer (`routers/`)

**Purpose:** Handle HTTP requests and responses

**What it does:**
- Defines API endpoints
- Validates incoming requests
- Delegates to controllers
- Formats HTTP responses
- Handles authentication/authorization

**Example:**
```python
@router.post("/register")
async def register(user_data: UserCreate):
    return await auth_controller.register_user(user_data)
```

**Files:**
- `auth.py` - `/api/v1/auth/*` endpoints
- `user.py` - `/api/v1/user/*` endpoints
- `conversation.py` - `/api/v1/conversations/*` endpoints
- `message.py` - `/api/v1/messages/*` endpoints

## Data Flow

```
1. Client Request
   ↓
2. Route (View Layer)
   - Validates request
   - Extracts data
   ↓
3. Controller (Controller Layer)
   - Processes business logic
   - Interacts with database
   ↓
4. Model (Model Layer)
   - Validates data
   - Ensures type safety
   ↓
5. Database
   - Stores/retrieves data
   ↓
6. Controller
   - Transforms data
   - Returns result
   ↓
7. Route
   - Formats HTTP response
   ↓
8. Client Response
```

## Database Collections

### Users Collection
- Stores user accounts and profiles
- Fields: name, email, password, grade, board, etc.
- Indexed on: email (unique), firebase_uid

### Conversations Collection
- Stores conversation threads
- Fields: user_id, title, timestamps
- Indexed on: user_id, updated_at

### Messages Collection
- Stores individual messages
- Fields: conversation_id, role, content, vector_embedding
- Indexed on: conversation_id, created_at

## Key Concepts

### Separation of Concerns
Each layer has a specific responsibility:
- **Models** = Data structure
- **Controllers** = Business logic
- **Routes** = HTTP handling

### Dependency Flow
```
Routes → Controllers → Models → Database
```

Routes depend on Controllers
Controllers depend on Models
Models are independent

### Error Handling
- Controllers raise `HTTPException`
- Routes catch and format errors
- Consistent error responses

### Authentication
- JWT tokens for authentication
- `get_current_user` dependency in routes
- Controllers receive user_id for authorization

## Usage Examples

### Creating a New Feature

1. **Define the Model** (`models/`)
```python
class FeatureCreate(BaseModel):
    name: str
    value: int
```

2. **Create the Controller** (`controllers/`)
```python
class FeatureController:
    async def create_feature(self, data: FeatureCreate):
        # Business logic here
        return result
```

3. **Add the Route** (`routers/`)
```python
@router.post("/features")
async def create_feature(data: FeatureCreate):
    return await feature_controller.create_feature(data)
```

4. **Register in main.py**
```python
from app.routers import feature
app.include_router(feature.router, prefix="/api/v1")
```

## Testing

### Unit Testing Controllers
```python
# Test business logic independently
controller = AuthController()
result = await controller.register_user(user_data)
assert result["user"]["email"] == "test@example.com"
```

### Integration Testing Routes
```python
# Test HTTP endpoints
response = client.post("/api/v1/auth/register", json=user_data)
assert response.status_code == 201
```

## Best Practices

1. **Keep routes thin** - Delegate to controllers
2. **Controllers return dicts** - Not HTTP responses
3. **Models validate data** - Use Pydantic
4. **Use type hints** - For better IDE support
5. **Handle errors in controllers** - Raise HTTPException
6. **Document endpoints** - Use docstrings
7. **Use async/await** - For database operations
8. **Follow naming conventions** - Clear and consistent

## Common Patterns

### Controller Pattern
```python
class SomeController:
    def __init__(self):
        self.collection = mongo_db["collection_name"]
    
    async def create_item(self, data: ItemCreate) -> Dict[str, Any]:
        # Validate
        # Process
        # Save to DB
        # Return result
        pass
```

### Route Pattern
```python
@router.post("/items", response_model=ItemResponse)
async def create_item(
    data: ItemCreate,
    current_user: dict = Depends(get_current_user)
):
    return await item_controller.create_item(
        current_user["_id"],
        data
    )
```

### Model Pattern
```python
class ItemBase(BaseModel):
    name: str

class ItemCreate(ItemBase):
    pass

class Item(ItemBase):
    id: str
    created_at: datetime
```

## Environment Variables

Required environment variables:
- `MONGODB_CONNECTION_STRING` - MongoDB connection string
- `SECRET_KEY` - JWT secret key
- `SARVAM_API_KEY` - Sarvam AI API key
- `GOOGLE_APPLICATION_CREDENTIALS` - Firebase credentials path

## Running the Application

```bash
# Activate virtual environment
source env/bin/activate

# Install dependencies
pip install -r requirements.txt

# Initialize database (first time only)
python -m app.db_utility.init_db

# Run the server
uvicorn app.main:app --reload

# Access API docs
open http://localhost:8000/docs
```

## Documentation

- **MVC_ARCHITECTURE.md** - Detailed architecture explanation
- **MIGRATION_GUIDE.md** - Migration and setup guide
- **API_REFERENCE.md** - Complete API documentation
- **SUMMARY.md** - Project overview

## Support

For questions about the architecture:
1. Review the MVC_ARCHITECTURE.md file
2. Check the specific layer's code
3. Look at similar implementations in the codebase
4. Refer to the API_REFERENCE.md for endpoint details

---

## Additional Setup Notes

### For STT (Speech-to-Text)
```bash
brew install ffmpeg
pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu118
pip install -U openai-whisper
```

### For TTS (Text-to-Speech using XTTS-v2)
```bash
# Example for CUDA 11.7
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu117
# For CPU only
pip install torch torchvision torchaudio
pip install TTS soundfile
```