# API Documentation

**Base URL:** `/api/v1`  
**Format:** JSON (request & response)  
**Auth:** Bearer token (JWT, 30-day expiry) — pass in `Authorization` header as `Bearer <token>`

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [User Profile](#2-user-profile)
3. [Conversations](#3-conversations)
4. [Messages](#4-messages)
5. [Agent (AI Tutor)](#5-agent-ai-tutor)
6. [Devices](#6-devices)
7. [Data Models](#7-data-models)
8. [Error Responses](#8-error-responses)

---

## 1. Authentication

**Prefix:** `/api/v1/auth`  
No authentication required for these endpoints.

---

### POST `/auth/register`
Register a new user with email and password.

**Request Body:**
```json
{
  "name": "Jane Doe",
  "email": "jane@example.com",
  "password": "secret123",
  "grade": "10",
  "board": "CBSE",
  "personalized_response": false
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | Yes | 1–100 chars |
| `email` | string (email) | Yes | |
| `password` | string | No | Min 6 chars |
| `grade` | string | No | Max 20 chars |
| `board` | string | No | Max 50 chars |
| `personalized_response` | boolean | No | Default: `false` |

**Response `201`:**
```json
{
  "message": "User registered successfully",
  "user": {
    "id": "uuid",
    "name": "Jane Doe",
    "email": "jane@example.com",
    "photo_url": null,
    "grade": "10",
    "board": "CBSE",
    "personalized_response": false
  },
  "token": "<jwt_token>"
}
```

**Errors:** `400` Email already registered

---

### POST `/auth/login`
Login with email and password.

**Request Body:**
```json
{
  "email": "jane@example.com",
  "password": "secret123"
}
```

**Response `200`:**
```json
{
  "message": "Login successful",
  "user": { ... },
  "token": "<jwt_token>"
}
```

**Errors:** `401` Invalid credentials

---

### POST `/auth/google`
Authenticate or register a user via Google Sign-In.

**Request Body:**
```json
{
  "id_token": "<firebase_google_id_token>"
}
```

**Response `200`:**
```json
{
  "message": "Login successful",
  "user": { ... },
  "token": "<jwt_token>"
}
```

**Errors:** `401` Invalid or expired Google token

---

## 2. User Profile

**Prefix:** `/api/v1/user`  
All endpoints require authentication.

---

### GET `/user/me`
Get the current user's profile.

**Response `200`:**
```json
{
  "id": "uuid",
  "name": "Jane Doe",
  "email": "jane@example.com",
  "photo_url": "https://...",
  "grade": "10",
  "board": "CBSE",
  "personalized_response": false,
  "account_type": "email",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-06-01T00:00:00Z"
}
```

**Errors:** `404` User not found

---

### PATCH `/user/me`
Update the current user's profile. Only provided fields are updated.

**Request Body** (all fields optional):
```json
{
  "name": "Jane Smith",
  "grade": "11",
  "board": "ICSE",
  "personalized_response": true,
  "photo_url": "https://..."
}
```

**Response `200`:** Updated user profile object (same shape as GET `/user/me`)

**Errors:** `404` User not found

---

### DELETE `/user/me`
Permanently delete the current user's account.

**Response `200`:**
```json
{
  "message": "User deleted successfully"
}
```

**Errors:** `404` User not found

---

## 3. Conversations

**Prefix:** `/api/v1/conversations`  
All endpoints require authentication.

---

### POST `/conversations`
Create a new conversation.

**Request Body:**
```json
{
  "topic": "Photosynthesis"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `topic` | string | Yes | 1–200 chars |

**Response `201`:**
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "topic": "Photosynthesis",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

---

### GET `/conversations`
List all conversations for the current user, sorted by most recent.

**Query Parameters:**

| Param | Type | Default | Notes |
|---|---|---|---|
| `skip` | integer | `0` | Pagination offset |
| `limit` | integer | `50` | Max 100 |

**Response `200`:** Array of conversation objects.

---

### GET `/conversations/{conversation_id}`
Get a specific conversation by ID.

**Response `200`:** A single conversation object.

**Errors:** `404` Conversation not found

---

### PATCH `/conversations/{conversation_id}`
Update a conversation's topic.

**Request Body:**
```json
{
  "topic": "Advanced Photosynthesis"
}
```

**Response `200`:** Updated conversation object.

**Errors:** `404` Conversation not found

---

### DELETE `/conversations/{conversation_id}`
Delete a conversation and all its messages.

**Response `200`:**
```json
{
  "message": "Conversation deleted successfully"
}
```

**Errors:** `404` Conversation not found

---

## 4. Messages

**Prefix:** `/api/v1/messages`  
All endpoints require authentication.

---

### POST `/messages`
Add a message to a conversation.

**Request Body:**
```json
{
  "conversation_id": "uuid",
  "role": "human",
  "content": "What is photosynthesis?"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `conversation_id` | string (uuid) | Yes | Must belong to current user |
| `role` | string | Yes | `"human"` or `"ai"` |
| `content` | string | Yes | Min 1 char |

**Response `201`:**
```json
{
  "conversation_id": "uuid",
  "role": "human",
  "content": "What is photosynthesis?",
  "created_at": "2024-01-01T00:00:00Z"
}
```

**Errors:** `404` Conversation not found

---

### GET `/messages/conversation/{conversation_id}`
Get all messages in a conversation.

**Query Parameters:**

| Param | Type | Default | Notes |
|---|---|---|---|
| `skip` | integer | `0` | Pagination offset |
| `limit` | integer | `100` | Max 500 |

**Response `200`:**
```json
[
  {
    "conversation_id": "uuid",
    "role": "human",
    "content": "What is photosynthesis?",
    "created_at": "2024-01-01T00:00:00Z"
  },
  {
    "conversation_id": "uuid",
    "role": "ai",
    "content": "Photosynthesis is the process by which...",
    "created_at": "2024-01-01T00:00:01Z"
  }
]
```

**Errors:** `404` Conversation not found

---

## 5. Agent (AI Tutor)

**Prefix:** `/api/v1/agent`  
All endpoints require authentication.

The agent is a guided AI tutor powered by Gemini. It maintains per-user session memory and supports both text and voice interaction. It classifies queries, generates lesson plans, evaluates understanding, and adapts its responses accordingly.

---

### POST `/agent/query`
Send a text query to the AI tutor. Returns a text response.

**Request Body:**
```json
{
  "query": "Explain Newton's second law"
}
```

**Response `200`:**
```json
{
  "response": "Newton's second law states that..."
}
```

> The agent automatically creates or resumes the user's session. Session memory persists across requests.

---

### POST `/agent/device-voice-assistant`
Send raw WAV audio to the AI tutor. Transcribes the speech, runs the agent, and streams back a TTS audio response.

**Request:**
- `Content-Type: audio/wav` (raw binary body)
- Audio format: 32-bit PCM WAV, 16 kHz, mono

**Response `200`:**
- `Content-Type: audio/mpeg`
- Streaming binary audio (MP3)
- Supports **interruption**: sending a new request while audio is streaming will cancel the active stream and start a new one.

**Headers returned:**
```
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

> Language is auto-detected from the audio. TTS output language matches the detected source language.

---

## 6. Devices

**Prefix:** `/api/v1/devices`

---

### POST `/devices/online/{device_id}`
Notify the server that a device is online.

**Path Parameter:** `device_id` — identifier for the device.

**Request Body:**
```json
{
  "device_id": "device-abc",
  "status": "online"
}
```

**Response `200`:**
```json
{
  "message": "Device online"
}
```

---

## 7. Data Models

### User
| Field | Type | Description |
|---|---|---|
| `id` | string | Unique user ID (UUID) |
| `name` | string | Display name |
| `email` | string | Email address |
| `photo_url` | string \| null | Profile photo URL |
| `grade` | string \| null | Academic grade |
| `board` | string \| null | Academic board (e.g., CBSE) |
| `personalized_response` | boolean | Enable personalized AI responses |
| `account_type` | string | `"email"` or `"google"` |
| `created_at` | datetime | Account creation timestamp |
| `updated_at` | datetime \| null | Last profile update timestamp |

### Conversation
| Field | Type | Description |
|---|---|---|
| `id` | string | Unique conversation ID (UUID) |
| `user_id` | string | Owner's user ID |
| `topic` | string | Conversation topic/subject |
| `created_at` | datetime | Creation timestamp |
| `updated_at` | datetime | Last update timestamp |

### Message
| Field | Type | Description |
|---|---|---|
| `conversation_id` | string | Parent conversation ID |
| `role` | string | `"human"` or `"ai"` |
| `content` | string | Message text content |
| `created_at` | datetime | Message timestamp |

---

## 8. Error Responses

All errors follow this structure:
```json
{
  "detail": "Human-readable error message"
}
```

| Status Code | Meaning |
|---|---|
| `400` | Bad Request — invalid input or duplicate resource |
| `401` | Unauthorized — missing, invalid, or expired token |
| `404` | Not Found — requested resource does not exist |
| `422` | Unprocessable Entity — request body validation failed |
| `500` | Internal Server Error — unexpected server-side failure |

### Authentication Errors

Protected endpoints return `401` with:
```json
{
  "detail": "Could not validate credentials"
}
```
Ensure the `Authorization` header is set to `Bearer <token>`.
