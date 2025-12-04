# API Quick Reference

## Base URL
```
http://localhost:8000/api/v1
```

## Authentication

All protected endpoints require a JWT token in the Authorization header:
```
Authorization: Bearer <your_jwt_token>
```

---

## 🔐 Authentication Endpoints

### Register User
```http
POST /auth/register
Content-Type: application/json

{
  "name": "John Doe",
  "email": "john@example.com",
  "password": "securepassword123",
  "grade": "10",              // Optional
  "board": "CBSE",            // Optional
  "personalized_response": true  // Optional, default: false
}
```

**Response:**
```json
{
  "message": "User registered successfully",
  "user": {
    "id": "uuid",
    "name": "John Doe",
    "email": "john@example.com",
    "photo_url": null,
    "grade": "10",
    "board": "CBSE",
    "personalized_response": true
  },
  "token": "jwt_token_here"
}
```

### Login
```http
POST /auth/login
Content-Type: application/json

{
  "email": "john@example.com",
  "password": "securepassword123"
}
```

**Response:**
```json
{
  "message": "Login successful",
  "user": { /* user object */ },
  "token": "jwt_token_here"
}
```

### Google Sign-In
```http
POST /auth/google
Content-Type: application/json

{
  "id_token": "firebase_id_token"
}
```

**Response:**
```json
{
  "message": "Google authentication successful",
  "user": { /* user object */ },
  "token": "jwt_token_here"
}
```

---

## 👤 User Profile Endpoints

### Get Current User Profile
```http
GET /user/me
Authorization: Bearer <token>
```

**Response:**
```json
{
  "id": "uuid",
  "name": "John Doe",
  "email": "john@example.com",
  "photo_url": "https://...",
  "grade": "10",
  "board": "CBSE",
  "personalized_response": true,
  "account_type": "email",
  "created_at": "2025-11-29T12:00:00Z",
  "updated_at": "2025-11-29T12:30:00Z"
}
```

### Update User Profile
```http
PATCH /user/me
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "John Updated",     // Optional
  "grade": "11",              // Optional
  "board": "ICSE",            // Optional
  "personalized_response": false  // Optional
}
```

**Response:**
```json
{
  "id": "uuid",
  "name": "John Updated",
  /* ... updated user object ... */
}
```

### Delete User Account
```http
DELETE /user/me
Authorization: Bearer <token>
```

**Response:**
```json
{
  "message": "User account deleted successfully"
}
```

---

## 💬 Conversation Endpoints

### Create Conversation
```http
POST /conversations
Authorization: Bearer <token>
Content-Type: application/json

{
  "topic": "Math Homework Help"
}
```

**Response:**
```json
{
  "id": "conversation_uuid",
  "user_id": "user_uuid",
  "topic": "Math Homework Help",
  "created_at": "2025-11-29T12:00:00Z"
}
```

### List All Conversations
```http
GET /conversations?skip=0&limit=50
Authorization: Bearer <token>
```

**Query Parameters:**
- `skip` (optional): Number of records to skip (default: 0)
- `limit` (optional): Max records to return (default: 50, max: 100)

**Response:**
```json
[
  {
    "id": "conversation_uuid",
    "user_id": "user_uuid",
    "topic": "Math Homework Help",
    "created_at": "2025-11-29T12:00:00Z"
  },
  /* ... more conversations ... */
]
```

### Get Specific Conversation
```http
GET /conversations/{conversation_id}
Authorization: Bearer <token>
```

**Response:**
```json
{
  "id": "conversation_uuid",
  "user_id": "user_uuid",
  "topic": "Math Homework Help",
  "created_at": "2025-11-29T12:00:00Z"
}
```

### Update Conversation
```http
PATCH /conversations/{conversation_id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "topic": "Updated Topic"
}
```

**Response:**
```json
{
  "id": "conversation_uuid",
  "user_id": "user_uuid",
  "topic": "Updated Topic",
  "created_at": "2025-11-29T12:00:00Z"
}
```

### Delete Conversation
```http
DELETE /conversations/{conversation_id}
Authorization: Bearer <token>
```

**Response:**
```json
{
  "message": "Conversation deleted successfully"
}
```

**Note:** Deleting a conversation also deletes its session and messages.

---

## 💭 Message Endpoints

### Create Message
```http
POST /messages
Authorization: Bearer <token>
Content-Type: application/json

{
  "conversation_id": "conversation_uuid",
  "role": "user",  // "user" or "assistant"
  "content": "What is the Pythagorean theorem?"
}
```

**Response:**
```json
{
  "conversation_id": "conversation_uuid",
  "role": "user",
  "content": "What is the Pythagorean theorem?",
  "created_at": "2025-11-29T12:00:00Z"
}
```

### Get Conversation Messages
```http
GET /messages/conversation/{conversation_id}?skip=0&limit=100
Authorization: Bearer <token>
```

**Query Parameters:**
- `skip` (optional): Number of records to skip (default: 0)
- `limit` (optional): Max records to return (default: 100, max: 500)

**Response:**
```json
[
  {
    "role": "user",
    "content": "What is the Pythagorean theorem?",
    "created_at": "2025-11-29T12:00:00Z"
  },
  {
    "role": "assistant",
    "content": "The Pythagorean theorem states that...",
    "created_at": "2025-11-29T12:00:05Z"
  }
]
```

---

## 📋 Error Responses

All endpoints may return the following error responses:

### 400 Bad Request
```json
{
  "detail": "Email already registered"
}
```

### 401 Unauthorized
```json
{
  "detail": "Could not validate credentials"
}
```

### 403 Forbidden
```json
{
  "detail": "Unauthorized access to message"
}
```

### 404 Not Found
```json
{
  "detail": "Conversation not found"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Authentication error: ..."
}
```

---

## 🔄 Common Workflows

### 1. User Registration & Login Flow
```bash
# 1. Register
POST /auth/register
# Save the token from response

# 2. Get profile
GET /user/me
Authorization: Bearer <token>

# 3. Update profile
PATCH /user/me
Authorization: Bearer <token>
```

### 2. Conversation Flow
```bash
# 1. Create conversation
POST /conversations
Authorization: Bearer <token>
# Save conversation_id from response

# 2. Add user message
POST /messages
Authorization: Bearer <token>
{
  "conversation_id": "<conversation_id>",
  "role": "user",
  "content": "Hello"
}

# 3. Add assistant response
POST /messages
Authorization: Bearer <token>
{
  "conversation_id": "<conversation_id>",
  "role": "assistant",
  "content": "Hi! How can I help?"
}

# 4. Get all messages
GET /messages/conversation/<conversation_id>
Authorization: Bearer <token>
```

### 3. List & Manage Conversations
```bash
# 1. List all conversations
GET /conversations?skip=0&limit=50
Authorization: Bearer <token>

# 2. Get specific conversation
GET /conversations/<conversation_id>
Authorization: Bearer <token>

# 3. Update conversation topic
PATCH /conversations/<conversation_id>
Authorization: Bearer <token>
{
  "topic": "New Topic"
}

# 4. Delete conversation
DELETE /conversations/<conversation_id>
Authorization: Bearer <token>
```

---

## 🧪 Testing with cURL

### Register User
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test User",
    "email": "test@example.com",
    "password": "password123"
  }'
```

### Login
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123"
  }'
```

### Get Profile
```bash
curl -X GET http://localhost:8000/api/v1/user/me \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### Create Conversation
```bash
curl -X POST http://localhost:8000/api/v1/conversations \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Math Help"
  }'
```

### Create Message
```bash
curl -X POST http://localhost:8000/api/v1/messages \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": "CONVERSATION_ID_HERE",
    "role": "user",
    "content": "What is calculus?"
  }'
```

---

## 📚 Interactive Documentation

FastAPI provides automatic interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

These interfaces allow you to:
- View all endpoints
- Test endpoints directly in the browser
- See request/response schemas
- Try authentication

---

## 💡 Tips

1.  **Always include the Authorization header** for protected endpoints
2.  **Save the JWT token** after login/register for subsequent requests
3.  **Use pagination** for large result sets (conversations, messages)
4.  **Check error responses** for detailed error messages
5.  **Use the interactive docs** at `/docs` for easy testing
6.  **Conversation IDs are required** when creating messages
7.  **Deleting a conversation** also deletes its session and messages
8.  **Deleting a user** also deletes all conversations and messages

---

## 🔗 Related Documentation

- `MVC_ARCHITECTURE.md` - Architecture details
- `MIGRATION_GUIDE.md` - Migration and setup guide
- `SUMMARY.md` - Project overview
