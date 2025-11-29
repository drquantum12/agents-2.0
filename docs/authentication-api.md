# Authentication API Documentation

This document outlines the authentication endpoints available in the backend API.

**Base URL:** `/api/v1`

**Authentication:** Protected endpoints require a JWT token in the `Authorization` header as `Bearer <token>`

---

## Authentication Endpoints

### 1. User Registration (Email & Password)

**Endpoint:** `/api/v1/auth/register`  
**Method:** `POST`  
**Authentication:** Public  
**Description:** Creates a new user account with email and password.

#### Request Body
```json
{
  "name": "Jane Doe",
  "email": "jane.doe@example.com",
  "password": "securepassword123"
}
```

#### Success Response (201 Created)
```json
{
  "message": "User registered successfully",
  "user": {
    "id": "uuid-1234-abcd",
    "name": "Jane Doe",
    "email": "jane.doe@example.com",
    "photo_url": null
  },
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

#### Error Responses
- **400 Bad Request:** Email already registered
```json
{
  "detail": "Email already registered"
}
```

---

### 2. User Login (Email & Password)

**Endpoint:** `/api/v1/auth/login`  
**Method:** `POST`  
**Authentication:** Public  
**Description:** Authenticates an existing user with email and password.

#### Request Body
```json
{
  "email": "jane.doe@example.com",
  "password": "securepassword123"
}
```

#### Success Response (200 OK)
```json
{
  "message": "Login successful",
  "user": {
    "id": "uuid-1234-abcd",
    "name": "Jane Doe",
    "email": "jane.doe@example.com",
    "photo_url": null
  },
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

#### Error Responses
- **401 Unauthorized:** Invalid credentials
```json
{
  "detail": "Invalid credentials"
}
```

---

### 3. Google Sign-In/Sign-Up

**Endpoint:** `/api/v1/auth/google`  
**Method:** `POST`  
**Authentication:** Public  
**Description:** Authenticates or registers a user using Firebase ID token from Google Sign-In.

#### Request Body
```json
{
  "id_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjVhOGEwNmMzNWMzN2..."
}
```

#### Success Response (200 OK)
```json
{
  "message": "Google authentication successful",
  "user": {
    "id": "google-user-12345",
    "name": "Jane Doe",
    "email": "jane.doe.google@gmail.com",
    "photo_url": "https://lh3.googleusercontent.com/a/..."
  },
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

#### Error Responses
- **400 Bad Request:** Token missing email
```json
{
  "detail": "Google token missing email"
}
```

- **401 Unauthorized:** Invalid Firebase token
```json
{
  "detail": "Invalid Firebase token: <error_message>"
}
```

- **500 Internal Server Error:** Authentication error
```json
{
  "detail": "Authentication error: <error_message>"
}
```

---

## User Profile Endpoints

### 4. Get Current User Profile

**Endpoint:** `/api/v1/user/me`  
**Method:** `GET`  
**Authentication:** Protected (Requires `Authorization: Bearer <token>`)  
**Description:** Retrieves the profile details of the currently authenticated user.

#### Request Headers
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

#### Success Response (200 OK)
```json
{
  "id": "uuid-1234-abcd",
  "name": "Jane Doe",
  "email": "jane.doe@example.com",
  "photo_url": "https://lh3.googleusercontent.com/a/...",
  "account_type": "email",
  "created_at": "2024-01-01T10:00:00Z",
  "updated_at": null
}
```

#### Error Responses
- **401 Unauthorized:** Invalid or missing token
```json
{
  "detail": "Could not validate credentials"
}
```

---

### 5. Update User Profile

**Endpoint:** `/api/v1/user/me`  
**Method:** `PATCH`  
**Authentication:** Protected (Requires `Authorization: Bearer <token>`)  
**Description:** Updates the authenticated user's profile details.

#### Request Headers
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json
```

#### Request Body
```json
{
  "name": "Jane Doe-Smith"
}
```

#### Success Response (200 OK)
```json
{
  "id": "uuid-1234-abcd",
  "name": "Jane Doe-Smith",
  "email": "jane.doe@example.com",
  "photo_url": "https://lh3.googleusercontent.com/a/...",
  "account_type": "email",
  "created_at": "2024-01-01T10:00:00Z",
  "updated_at": "2024-01-15T12:30:00Z"
}
```

#### Error Responses
- **401 Unauthorized:** Invalid or missing token
```json
{
  "detail": "Could not validate credentials"
}
```

---

## Authentication Flow

### Email/Password Flow
1. **Registration:** User sends credentials to `/auth/register`
2. **Backend:** Creates user in MongoDB with hashed password
3. **Response:** Returns user data and JWT token
4. **Subsequent Requests:** Client includes JWT in `Authorization` header

### Google Sign-In Flow
1. **Client:** User signs in with Google via Firebase Authentication
2. **Client:** Obtains Firebase ID token
3. **Client:** Sends ID token to `/auth/google`
4. **Backend:** Verifies token with Firebase Admin SDK
5. **Backend:** Creates new user or logs in existing user
6. **Response:** Returns user data and JWT token
7. **Subsequent Requests:** Client includes JWT in `Authorization` header

---

## Security Notes

- All passwords are hashed using bcrypt before storage
- JWT tokens expire after 30 days
- Firebase Admin SDK verifies Google Sign-In tokens using Firebase credentials
- Protected endpoints validate JWT tokens and fetch user data from MongoDB
- Email and password fields are read-only after account creation (except via password reset, if implemented)
