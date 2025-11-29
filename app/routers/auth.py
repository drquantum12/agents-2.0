from fastapi import APIRouter, HTTPException, status, Depends, Body
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timezone
import uuid
from app.db_utility.mongo_db import mongo_db
from app.utility.security import get_password_hash, verify_password, create_access_token
from app.utility.firebase_init import verify_firebase_token

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Models
class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class GoogleAuth(BaseModel):
    id_token: str

class UserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    photo_url: Optional[str] = None

class AuthResponse(BaseModel):
    message: str
    user: UserResponse
    token: str

# Endpoints

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister):
    users_collection = mongo_db["users"]
    
    if users_collection.find_one({"email": user_data.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    hashed_password = get_password_hash(user_data.password)
    
    new_user = {
        "_id": user_id,
        "name": user_data.name,
        "email": user_data.email,
        "password": hashed_password,
        "photo_url": None,
        "account_type": "email",
        "created_at": datetime.now(timezone.utc)
    }
    
    users_collection.insert_one(new_user)
    
    token = create_access_token({"sub": user_id})
    
    return {
        "message": "User registered successfully",
        "user": {
            "id": user_id,
            "name": new_user["name"],
            "email": new_user["email"],
            "photo_url": new_user["photo_url"]
        },
        "token": token
    }

@router.post("/login", response_model=AuthResponse)
async def login(login_data: UserLogin):
    users_collection = mongo_db["users"]
    user = users_collection.find_one({"email": login_data.email})
    
    if not user or not verify_password(login_data.password, user.get("password", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"sub": user["_id"]})
    
    return {
        "message": "Login successful",
        "user": {
            "id": user["_id"],
            "name": user["name"],
            "email": user["email"],
            "photo_url": user.get("photo_url")
        },
        "token": token
    }

@router.post("/google", response_model=AuthResponse)
async def google_auth(auth_data: GoogleAuth):
    try:
        # Verify the token with Firebase Admin SDK
        decoded_token = verify_firebase_token(auth_data.id_token)
        
        # Extract user information from the decoded token
        email = decoded_token.get("email")
        name = decoded_token.get("name")
        photo_url = decoded_token.get("picture")
        firebase_uid = decoded_token.get("uid")
        
        if not email:
            raise HTTPException(status_code=400, detail="Google token missing email")

        users_collection = mongo_db["users"]
        user = users_collection.find_one({"email": email})
        
        if user:
            # Login existing user - update photo_url if it changed
            if photo_url and user.get("photo_url") != photo_url:
                users_collection.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"photo_url": photo_url}}
                )
                user["photo_url"] = photo_url
                
            token = create_access_token({"sub": user["_id"]})
            user_response = {
                "id": user["_id"],
                "name": user["name"],
                "email": user["email"],
                "photo_url": user.get("photo_url")
            }
            message = "Google authentication successful"
        else:
            # Register new user
            user_id = str(uuid.uuid4())
            new_user = {
                "_id": user_id,
                "name": name,
                "email": email,
                "photo_url": photo_url,
                "account_type": "google",
                "firebase_uid": firebase_uid,
                "created_at": datetime.now(timezone.utc)
            }
            users_collection.insert_one(new_user)
            token = create_access_token({"sub": user_id})
            user_response = {
                "id": user_id,
                "name": name,
                "email": email,
                "photo_url": photo_url
            }
            message = "Google authentication successful"
            
        return {
            "message": message,
            "user": user_response,
            "token": token
        }

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication error: {str(e)}")
