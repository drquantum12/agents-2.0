# API Documentation

**Base URL:** `/api/v1`  
**Format:** JSON (request & response)  
**Auth:** Bearer token (JWT, 30-day expiry) — pass in `Authorization` header as `Bearer <token>`

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [User Profile](#2-user-profile)
   - [GET /user/me](#get-userme)
   - [PATCH /user/me](#patch-userme)
   - [DELETE /user/me](#delete-userme)
3. [Conversations](#3-conversations)
4. [Messages](#4-messages)
5. [Agent (AI Tutor)](#5-agent-ai-tutor)
   - [POST /agent/query](#post-agentquery)
   - [POST /agent/device-voice-assistant](#post-agentdevice-voice-assistant)
   - [WS /agent/device-voice-assistant-ws](#ws-agentdevice-voice-assistant-ws)
   - [POST /agent/device-voice-assistant-test](#post-agentdevice-voice-assistant-test)
6. [Devices](#6-devices)
   - [POST /devices/online/{device_id}](#post-devicesonlinedevice_id)
   - [POST /devices/heartbeat/{device_id}](#post-devicesheartbeatdevice_id)
   - [GET /devices/mine](#get-devicesmine)
   - [GET /devices/{device_id}/status](#get-devicesdevice_idstatus)
   - [POST /devices/{device_id}/unpair](#post-devicesdevice_idunpair)
   - [GET /devices/{device_id}/history](#get-devicesdevice_idhistory)
   - [GET /devices/config](#get-devicesconfig)
   - [PATCH /devices/config](#patch-devicesconfig)
   - [GET /devices/firmware/download](#get-devicesfirmwaredownload)
7. [Notifications](#7-notifications)
   - [GET /notifications](#get-notifications)
   - [DELETE /notifications/{notification_id}](#delete-notificationsnotification_id)
8. [MQTT](#8-mqtt)
   - [POST /mqtt/publish](#post-mqttpublish)
9. [Orders (Razorpay)](#9-orders-razorpay)
   - [POST /orders/create](#post-orderscreate)
   - [POST /orders/verify](#post-ordersverify)
   - [GET /orders/status/{order_id}](#get-ordersstatusorder_id)
   - [POST /orders/webhook](#post-orderswebhook)
   - [GET /orders/get/{email}](#get-ordersgetemail)
   - [POST /orders/notify-on-new-device](#post-ordersnotify-on-new-device)
10. [Data Models](#10-data-models)
11. [Error Responses](#11-error-responses)

---

## 1. Authentication

**Prefix:** `/api/v1/auth`  
No authentication required for these endpoints.

---

### POST `/auth/register`
Register a new user. The Firebase account must already be created on the client
(via `createUserWithEmailAndPassword`). This endpoint persists the user profile
in the backend database.

> **How to get the token:** After `createUserWithEmailAndPassword(auth, email, password)`
> succeeds, call `user.getIdToken()` and include it as `id_token`.
> Email is extracted server-side from the token — do **not** send the raw password.

**Request Body:**
```json
{
  "id_token": "<firebase_id_token>",
  "name": "Jane Doe",
  "grade": "10",
  "board": "CBSE",
  "personalized_response": false
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `id_token` | string | Yes | Firebase ID token from `createUserWithEmailAndPassword` → `user.getIdToken()` |
| `name` | string | Yes | 1–100 chars |
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

**Errors:** `400` Email already registered · `400` Token missing email claim · `401` Invalid/expired Firebase token

---

### POST `/auth/login`
Login with email and password using a Firebase ID token.

> **Note:** The backend no longer accepts a raw email + password. After calling
> `signInWithEmailAndPassword(email, password)` (or after a password reset),
> call `user.getIdToken()` on the Firebase user object and send that token here.
> This keeps Firebase as the single source of truth for credentials and ensures
> password resets work correctly.

**Request Body:**
```json
{
  "id_token": "<firebase_id_token>"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `id_token` | string | Yes | Firebase ID token from `signInWithEmailAndPassword` → `user.getIdToken()` |

**Response `200`:**
```json
{
  "message": "Login successful",
  "user": { ... },
  "token": "<jwt_token>"
}
```

**Errors:** `400` Token missing email claim · `401` Invalid/expired Firebase token · `401` No account found for this email

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
All endpoints require authentication unless stated otherwise.

The agent is a guided AI tutor powered by Gemini. It maintains per-user session memory and supports both text and voice interaction. It classifies queries, generates lesson plans, evaluates understanding, and adapts its responses accordingly.

---

### POST `/agent/query`
Send a text query to the AI tutor. Returns a text response.

**Auth:** Required

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

**Auth:** Required

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

> Language is auto-detected from the audio. TTS output language matches the detected source language. Supported languages: English, Hindi, Bengali, Gujarati, Kannada, Malayalam, Marathi, Odia, Punjabi, Tamil, Telugu.

---

### WS `/agent/device-voice-assistant-ws`
WebSocket endpoint for the AI device voice assistant. Designed for embedded/IoT clients that cannot send an `Authorization` header — authentication is done via a query-parameter token.

**Auth:** Token passed as query parameter `?token=<jwt_token>`

**Connection URL:** `ws://<host>/api/v1/agent/device-voice-assistant-ws?token=<jwt_token>`

**Protocol:**

| Direction | Frame Type | Description |
|---|---|---|
| Device → Server | Binary | Raw WAV audio bytes |
| Server → Device | Binary | MP3 audio chunks (streamed as they arrive) |
| Server → Device | Text `"DONE"` | Response stream finished |
| Server → Device | Text `"ERROR:<msg>"` | Processing error |

Sending new audio while a response is still streaming cancels the in-flight stream immediately and starts processing the new utterance.

**Close Codes:**
- `4001` — Invalid or missing token / user not found

---

### POST `/agent/device-voice-assistant-test`
Development/testing endpoint that returns a simulated MP3 audio stream with randomised network jitter. Accepts a raw body (ignored) and streams back canned audio.

**Auth:** Not required

**Request:** Raw body (any, ignored)

**Response `200`:**
- `Content-Type: audio/mpeg`
- Simulated streaming binary audio (MP3)

---

## 6. Devices

**Prefix:** `/api/v1/devices`  
Endpoints marked **Auth required** need `Authorization: Bearer <token>`.

> **Rate limit:** `POST /devices/online/{device_id}` is limited to **5 requests per minute per device**. Exceeding this returns `429 Too Many Requests`.

---

### POST `/devices/online/{device_id}`
Called by the IoT device after every successful WiFi connection. Manages device ownership atomically — handles first claim, re-provisioning by the same user, and ownership transfer.

**Auth:** Required  
**Path Parameter:** `device_id` — hardware serial or MAC address (used as `_id` in the `devices` collection).

**Request Body:**
```json
{
  "firmware_version": 0.1,
  "hardware_revision": "rev-B"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `firmware_version` | float | Yes | Current firmware version number |
| `hardware_revision` | string | No | Hardware revision identifier |

**Response `200` — Brand-new device (first claim):**
```json
{ "status": "claimed", "device_id": "esp32-aabbcc" }
```

**Response `200` — Same user re-provisioning:**
```json
{ "status": "re_provisioned", "device_id": "esp32-aabbcc" }
```

**Response `200` — Ownership transferred to new user:**
```json
{ "status": "transferred", "device_id": "esp32-aabbcc" }
```

**Errors:** `401` Unauthorized (causes ESP32 FSM to re-enter BLE config mode), `429` Rate limit exceeded

---

### POST `/devices/heartbeat/{device_id}`
Called periodically by the IoT device to signal that it is still online. Updates `last_seen_at`, `ip_address`, and `is_online` on the device document. Only the current owner's token is accepted.

**Auth:** Required  
**Path Parameter:** `device_id` — hardware serial or MAC address.

**Request Body:** None

**Response `204`:** No content (empty body on success)

**Errors:** `401` Unauthorized, `404` Device not found or not owned by you

---

### GET `/devices/mine`
Returns all active devices currently owned by the authenticated user.

**Auth:** Required

**Response `200`:**
```json
{
  "devices": [
    {
      "device_id": "esp32-aabbcc",
      "firmware_version": 0.1,
      "ownership_status": "active",
      "is_online": true,
      "last_seen_at": "2026-03-07T08:00:00Z"
    }
  ]
}
```

**Errors:** `401` Unauthorized

---

### GET `/devices/{device_id}/status`
Returns the online status and ownership info for a specific device. Only the current owner may query this.

**Auth:** Required  
**Path Parameter:** `device_id`

**Response `200`:**
```json
{
  "device_id": "esp32-aabbcc",
  "is_online": true,
  "ownership_status": "active",
  "last_seen_at": "2026-03-07T08:00:00Z",
  "firmware_version": 0.1
}
```

**Errors:** `401` Unauthorized, `403` Not your device, `404` Device not found

---

### POST `/devices/{device_id}/unpair`
Voluntarily releases the user's ownership of a device. Sets the device to `unclaimed` and clears `device_id` from the user's `device_config`.

**Auth:** Required  
**Path Parameter:** `device_id`

**Response `200`:**
```json
{ "success": true }
```

**Errors:** `401` Unauthorized, `403` Not your device, `404` Device not found

---

### GET `/devices/{device_id}/history`
Returns the full append-only ownership history for a device. Only the current owner may query this.

**Auth:** Required  
**Path Parameter:** `device_id`

**Response `200`:**
```json
{
  "device_id": "esp32-aabbcc",
  "ownership_history": [
    {
      "user_id": "uuid-user-1",
      "claimed_at": "2026-01-01T10:00:00Z",
      "released_at": "2026-02-15T09:30:00Z",
      "release_reason": "transfer",
      "transfer_to_user": "uuid-user-2"
    },
    {
      "user_id": "uuid-user-2",
      "claimed_at": "2026-02-15T09:30:00Z",
      "released_at": null,
      "release_reason": null,
      "transfer_to_user": null
    }
  ]
}
```

**Errors:** `401` Unauthorized, `403` Not your device, `404` Device not found

---

### GET `/devices/config`
Get the device configuration for the currently authenticated user. If no configuration exists, a default one is automatically created and returned.

**Auth:** Required (Bearer token)

**Response `200`:**
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "learning_mode": "Normal",
  "response_type": "Detailed",
  "difficulty_level": "Beginner",
  "created_at": "2026-03-06T10:00:00Z",
  "updated_at": null
}
```

**Errors:** `401` Unauthorized

---

### PATCH `/devices/config`
Partially update the device configuration for the currently authenticated user. Only include the fields you want to change.

**Auth:** Required (Bearer token)

**Request Body** (all fields optional):
```json
{
  "learning_mode": "Strict",
  "response_type": "Concise",
  "difficulty_level": "Advanced"
}
```

| Field | Type | Required | Allowed Values |
|---|---|---|---|
| `learning_mode` | string | No | `"Strict"`, `"Normal"` |
| `response_type` | string | No | `"Detailed"`, `"Concise"` |
| `difficulty_level` | string | No | `"Beginner"`, `"Intermediate"`, `"Advanced"` |

**Response `200`:**
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "learning_mode": "Strict",
  "response_type": "Concise",
  "difficulty_level": "Advanced",
  "created_at": "2026-03-06T10:00:00Z",
  "updated_at": "2026-03-06T12:30:00Z"
}
```

**Errors:** `400` Invalid field value, `401` Unauthorized

---

### GET `/devices/firmware/download`
Downloads the latest firmware binary from Google Cloud Storage. The device calls this endpoint to self-update.

The server resolves the latest version from the `firmware` MongoDB collection (highest `version` value), then streams the corresponding `.bin` file from the `vijayebhav-firmware` GCS bucket as a `FileResponse` (automatically sets `Content-Length`).

**Auth:** Not required — open endpoint intended for IoT devices.

**Response `200`:**
- `Content-Type: application/octet-stream`
- `Content-Disposition: attachment; filename="firmware_v<version>.bin"`
- Binary `.bin` file body

**Errors:**
- `404` No firmware versions found (empty `firmware` collection)
- `404` Firmware blob not found in GCS
- `500` Error downloading firmware (GCS SDK or I/O error)

## 7. Notifications

**Prefix:** `/api/v1/notifications`  
All endpoints require authentication.

---

### GET `/notifications`
Get paginated notifications for the current user. Returns 5 notifications per page, sorted newest first.

**Query Parameters:**

| Param | Type | Default | Notes |
|---|---|---|---|
| `page` | integer | `1` | 1-based page number, must be ≥ 1 |

**Response `200`:**
```json
{
  "page": 1,
  "page_size": 5,
  "total": 23,
  "has_next": true,
  "notifications": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "message": "Your session is about to expire.",
      "type": "warn",
      "created_at": "2026-03-06T10:00:00Z"
    }
  ]
}
```

| Response Field | Type | Description |
|---|---|---|
| `page` | integer | Current page number |
| `page_size` | integer | Number of items per page (always `5`) |
| `total` | integer | Total notifications for this user |
| `has_next` | boolean | Whether more pages exist |
| `notifications` | array | Array of notification objects |

**Errors:** `400` Invalid page number, `401` Unauthorized

---

### DELETE `/notifications/{notification_id}`
Delete a specific notification by its ID. The notification must belong to the authenticated user.

**Path Parameter:** `notification_id` — The `_id` of the notification to delete.

**Response `200`:**
```json
{
  "message": "Notification deleted successfully"
}
```

**Errors:** `401` Unauthorized, `404` Notification not found

---

## 8. MQTT

**Prefix:** `/api/v1/mqtt`  
All endpoints require authentication. Used to publish raw command messages to IoT devices over HiveMQ Cloud.

---

### POST `/mqtt/publish`
Publish a message to an arbitrary MQTT topic. The backend forwards it to the HiveMQ Cloud broker at the specified QoS level.

**Auth:** Required

**Request Body:**
```json
{
  "topic": "devices/esp32-aabbcc/commands",
  "message": "reboot",
  "qos": 0
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `topic` | string | Yes | MQTT topic string, e.g. `devices/esp32-aabbcc/commands` |
| `message` | string | Yes | Raw message payload |
| `qos` | integer | No | Quality of Service level: `0`, `1`, or `2`. Default: `0` |

**Response `200`:**
```json
{ "status": "Message published successfully" }
```

**Errors:** `401` Unauthorized

> **Note:** The unpair flow also internally publishes the string `"unpair"` to `devices/{device_id}/commands` (QoS 1) via this same HiveMQ client — directly in `POST /devices/{device_id}/unpair`, not through this endpoint.

---

## 9. Orders (Razorpay)

**Prefix:** `/api/v1/orders`

> **Note:** The orders router (`app/routers/orders.py`) must be included in `main.py` via `app.include_router(orders.router, prefix="/api/v1")` to activate these endpoints.

Handles product purchases and pre-orders through Razorpay. Orders are stored in the `orders` MongoDB collection.

---

### POST `/orders/create`
Creates a new Razorpay order and persists it in the database with `status: "pending"`.

**Auth:** Not required

**Request Body:**
```json
{
  "amount": 2500,
  "product_id": "prod_abc123",
  "order_type": "preorder",
  "name": "Jane Doe",
  "email": "user@example.com",
  "phone": "9876543210",
  "house_no": "42B",
  "locality": "MG Road",
  "city": "Bengaluru",
  "state": "Karnataka",
  "pincode": "560001"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `amount` | integer | Yes | Amount in INR (converted to paise internally) |
| `product_id` | string | Yes | Product identifier |
| `order_type` | string | Yes | `"buy"` or `"preorder"` |
| `name` | string | Yes | Buyer's full name |
| `email` | string (email) | Yes | Buyer's email address |
| `phone` | string | Yes | Buyer's phone number |
| `house_no` | string | Yes | House/flat number |
| `locality` | string | Yes | Street / locality name |
| `city` | string | Yes | City |
| `state` | string | Yes | State |
| `pincode` | string | Yes | Postal code |

**Response `200`:**
```json
{
  "order_id": "order_razorpay_abc123",
  "amount": 999,
  "currency": "INR"
}
```

**Errors:** `500` Razorpay API failure

---

### POST `/orders/verify`
Verifies the Razorpay payment signature after the client-side checkout completes. Saves the `payment_id` and sets order status to `"processing"`. Does **not** confirm capture — use [`GET /orders/status/{order_id}`](#get-ordersstatusorder_id) to poll for the final `paid` or `failed` status set by the webhook.

**Auth:** Not required

**Request Body:**
```json
{
  "order_id": "order_razorpay_abc123",
  "payment_id": "pay_xyz789",
  "signature": "<razorpay_signature>"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `order_id` | string | Yes | Razorpay order ID returned from `/orders/create` |
| `payment_id` | string | Yes | Razorpay payment ID from checkout callback |
| `signature` | string | Yes | HMAC-SHA256 signature from Razorpay checkout callback |

**Response `200`:**
```json
{
  "success": true,
  "status": "processing"
}
```

**Errors:** `400` Invalid payment signature

---

### GET `/orders/status/{order_id}`
Polling endpoint to check the current status of an order. The frontend should call this every 2–3 seconds after `/orders/verify` until status becomes `"paid"` or `"failed"`. The `order` object is only returned when status is terminal (`paid` or `failed`).

**Auth:** Not required

**Path Parameter:** `order_id` — the Razorpay order ID.

**Response `200` (processing):**
```json
{
  "status": "processing",
  "order": null
}
```

**Response `200` (paid):**
```json
{
  "status": "paid",
  "order": {
    "razorpay_order_id": "order_razorpay_abc123",
    "name": "Jane Doe",
    "email": "user@example.com",
    "phone": "9876543210",
    "product_id": "prod_abc123",
    "amount": 2500,
    "order_type": "preorder",
    "status": "paid",
    "payment_id": "pay_xyz789",
    "house_no": "42B",
    "locality": "MG Road",
    "city": "Bengaluru",
    "state": "Karnataka",
    "pincode": "560001",
    "created_at": 1747123456.0,
    "updated_at": 1747123789.0
  }
}
```

**Response `200` (failed):**
```json
{
  "status": "failed",
  "order": { "..." }
}
```

**Errors:** `404` Order not found

> **Frontend note:** Set a polling timeout of ~2 minutes. If status is still `"processing"` after timeout, show a message to check email or contact support — the webhook may have been delayed.

---

### POST `/orders/webhook`
Razorpay webhook receiver. Verifies the webhook signature and updates the order status based on the event type.

**Auth:** Not required — validated via `X-Razorpay-Signature` header (HMAC-SHA256)

**Headers:**
```
X-Razorpay-Signature: <razorpay_webhook_signature>
```

**Request Body:** Raw JSON payload from Razorpay (sent by Razorpay servers directly)

**Supported Events:**

| Event | Effect |
|---|---|
| `payment.captured` | Sets order `status` → `"paid"`; sends a preorder confirmation email to the user (via Resend) if their account has an email address on record |
| `payment.failed` | Sets order `status` → `"failed"` |
| `refund.processed` | Sets order `status` → `"refunded"` |

> **Email on capture:** The `payment.captured` handler fetches the order by `razorpay_order_id` and uses the `email` field stored on the order document directly. It renders the `preorder_confirmation.html` template and sends it via Resend (`RESEND_FROM_EMAIL`, defaults to `no-reply@vijayebhav.com`). Requires `RESEND_API_KEY`.

**Response `200`:**
```json
{
  "success": true
}
```

**Errors:** `400` Invalid webhook signature

---

### GET `/orders/get/{email}`
Returns all orders placed by the given email address.

**Auth:** Not required

**Path Parameter:** `email` — the buyer's email address (URL-encoded).

**Response `200`:**
```json
[
  {
    "razorpay_order_id": "order_abc123",
    "email": "user@example.com",
    "phone": "9876543210",
    "product_id": "prod_xyz",
    "amount": 2500,
    "order_type": "preorder",
    "status": "paid",
    "payment_id": "pay_xyz789",
    "house_no": "42B",
    "locality": "MG Road",
    "city": "Bengaluru",
    "state": "Karnataka",
    "pincode": "560001",
    "created_at": 1747123456.0,
    "updated_at": 1747123789.0
  }
]
```

Returns an empty array `[]` if no orders exist for that email.

**Errors:** `422` Invalid path parameter

---

### POST `/orders/notify-on-new-device`
Registers a user to be notified when a new VijayeBhav device becomes available. Saves the entry in the `potential_customers` MongoDB collection and sends a confirmation email via Resend. If the email is already registered, returns a success response without creating a duplicate.

**Auth:** Not required

**Request Body:**
```json
{
  "name": "Jane Doe",
  "email": "user@example.com",
  "city": "Bengaluru",
  "state": "Karnataka"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | Yes | User's name (used in the notification email) |
| `email` | string (email) | Yes | Email to notify |
| `city` | string | No | User's city |
| `state` | string | No | User's state |

**Response `200` (new registration):**
```json
{
  "success": true
}
```

**Response `200` (already registered):**
```json
{
  "success": true,
  "message": "Already registered for notifications"
}
```

**Errors:** `422` Invalid email format

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

### Device
| Field | Type | Description |
|---|---|---|
| `device_id` | string | Hardware serial / MAC — primary key |
| `firmware_version` | float \| null | Current firmware version |
| `hardware_revision` | string \| null | Hardware revision identifier |
| `owner_user_id` | string \| null | Current owner's user ID (`null` = unclaimed) |
| `ownership_status` | string | `"unclaimed"`, `"active"`, or `"transferring"` |
| `claimed_at` | datetime \| null | When the current owner claimed the device |
| `last_provisioned_at` | datetime \| null | Last `POST /devices/online` timestamp |
| `is_online` | boolean | Whether device connected successfully last time |
| `last_seen_at` | datetime \| null | Last successful connection timestamp |
| `ip_address` | string \| null | Client IP at last connection |
| `pending_transfer` | object \| null | In-flight transfer window (TTL 15 min) |
| `ownership_history` | array | Append-only ownership audit trail (max 20 entries) |
| `created_at` | datetime | First registration timestamp |
| `updated_at` | datetime | Last document update timestamp |

### OwnershipHistoryEntry
| Field | Type | Description |
|---|---|---|
| `user_id` | string | User who held ownership |
| `claimed_at` | datetime | When ownership started |
| `released_at` | datetime \| null | When ownership ended (`null` = current owner) |
| `release_reason` | string \| null | `"transfer"`, `"manual_unpair"`, `"admin"`, or `"account_deleted"` |
| `transfer_to_user` | string \| null | Next owner's user ID (only set on `"transfer"`) |

### DeviceConfiguration
| Field | Type | Description |
|---|---|---|
| `id` | string | Unique config ID (UUID) |
| `user_id` | string | Owner's user ID |
| `device_id` | string \| null | Linked device hardware ID |
| `device_online` | boolean | Whether the linked device is currently online |
| `learning_mode` | string | `"Strict"` or `"Normal"` |
| `response_type` | string | `"Detailed"` or `"Concise"` |
| `difficulty_level` | string | `"Beginner"`, `"Intermediate"`, or `"Advanced"` |
| `created_at` | datetime | Config creation timestamp |
| `updated_at` | datetime \| null | Last update timestamp |

### Notification
| Field | Type | Description |
|---|---|---|
| `id` | string | Unique notification ID |
| `user_id` | string | Owner's user ID |
| `message` | string | Notification text |
| `type` | string | `"info"`, `"warn"`, or `"err"` |
| `created_at` | datetime | Creation timestamp |

### Order
| Field | Type | Description |
|---|---|---|
| `razorpay_order_id` | string | Razorpay-assigned order ID |
| `email` | string | Buyer's email address |
| `phone` | string | Buyer's phone number |
| `product_id` | string | Product identifier |
| `amount` | integer | Order amount in INR |
| `order_type` | string | `"buy"` or `"preorder"` |
| `status` | string | `"pending"`, `"paid"`, `"failed"`, or `"refunded"` |
| `payment_id` | string \| null | Razorpay payment ID (set after successful payment) |
| `house_no` | string | House / flat number |
| `locality` | string | Street / locality |
| `city` | string | City |
| `state` | string | State |
| `pincode` | string | Postal code |
| `created_at` | float | Unix timestamp of order creation |
| `updated_at` | float | Unix timestamp of last status update |

---

## 11. Error Responses

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
| `403` | Forbidden — authenticated but not authorised for this resource |
| `404` | Not Found — requested resource does not exist |
| `422` | Unprocessable Entity — request body validation failed |
| `429` | Too Many Requests — rate limit exceeded (retry after 60 s) |
| `500` | Internal Server Error — unexpected server-side failure |

### Authentication Errors

Protected endpoints return `401` with:
```json
{
  "detail": "Could not validate credentials"
}
```
Ensure the `Authorization` header is set to `Bearer <token>`.
