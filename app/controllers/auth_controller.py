from fastapi import HTTPException, status
from datetime import datetime, timezone
import uuid
from typing import Dict, Any

from app.models.user import UserCreate, UserInDB
from app.db_utility.mongo_db import mongo_db
from app.utility.security import get_password_hash, verify_password, create_access_token
from app.utility.firebase_init import verify_firebase_token


class AuthController:
    """Controller for handling authentication logic"""
    
    def __init__(self):
        self.users_collection = mongo_db["users"]
    
    async def register_user(self, user_data: UserCreate) -> Dict[str, Any]:
        """
        Register a new user with email and password
        
        Args:
            user_data: User registration data
            
        Returns:
            Dictionary containing user info and access token
            
        Raises:
            HTTPException: If email is already registered
        """
        # Check if user already exists
        if self.users_collection.find_one({"email": user_data.email}):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Create new user
        user_id = str(uuid.uuid4())
        hashed_password = get_password_hash(user_data.password) if user_data.password else None
        
        new_user = {
            "_id": user_id,
            "name": user_data.name,
            "email": user_data.email,
            "password": hashed_password,
            "photo_url": None,
            "grade": user_data.grade,
            "board": user_data.board,
            "personalized_response": user_data.personalized_response,
            "account_type": "email",
            "created_at": datetime.now(timezone.utc)
        }
        
        self.users_collection.insert_one(new_user)
        
        # Generate access token
        token = create_access_token({"sub": user_id})
        
        return {
            "message": "User registered successfully",
            "user": {
                "id": user_id,
                "name": new_user["name"],
                "email": new_user["email"],
                "photo_url": new_user["photo_url"],
                "grade": new_user.get("grade"),
                "board": new_user.get("board"),
                "personalized_response": new_user.get("personalized_response", False)
            },
            "token": token
        }
    
    async def login_user(self, email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate user with email and password
        
        Args:
            email: User email
            password: User password
            
        Returns:
            Dictionary containing user info and access token
            
        Raises:
            HTTPException: If credentials are invalid
        """
        user = self.users_collection.find_one({"email": email})
        
        if not user or not verify_password(password, user.get("password", "")):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        # Generate access token
        token = create_access_token({"sub": user["_id"]})
        
        return {
            "message": "Login successful",
            "user": {
                "id": user["_id"],
                "name": user["name"],
                "email": user["email"],
                "photo_url": user.get("photo_url"),
                "grade": user.get("grade"),
                "board": user.get("board"),
                "personalized_response": user.get("personalized_response", False)
            },
            "token": token
        }
    
    async def google_auth(self, id_token: str) -> Dict[str, Any]:
        """
        Authenticate or register user with Google Sign-In
        
        Args:
            id_token: Firebase ID token from Google Sign-In
            
        Returns:
            Dictionary containing user info and access token
            
        Raises:
            HTTPException: If token is invalid or authentication fails
        """
        try:
            # Verify the token with Firebase Admin SDK
            decoded_token = verify_firebase_token(id_token)
            
            # Extract user information
            email = decoded_token.get("email")
            name = decoded_token.get("name")
            photo_url = decoded_token.get("picture")
            firebase_uid = decoded_token.get("uid")
            
            if not email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Google token missing email"
                )
            
            user = self.users_collection.find_one({"email": email})
            
            if user:
                # Login existing user - update photo_url if it changed
                if photo_url and user.get("photo_url") != photo_url:
                    self.users_collection.update_one(
                        {"_id": user["_id"]},
                        {"$set": {"photo_url": photo_url}}
                    )
                    user["photo_url"] = photo_url
                
                token = create_access_token({"sub": user["_id"]})
                user_response = {
                    "id": user["_id"],
                    "name": user["name"],
                    "email": user["email"],
                    "photo_url": user.get("photo_url"),
                    "grade": user.get("grade"),
                    "board": user.get("board"),
                    "personalized_response": user.get("personalized_response", False)
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
                    "grade": None,
                    "board": None,
                    "personalized_response": False,
                    "account_type": "google",
                    "firebase_uid": firebase_uid,
                    "created_at": datetime.now(timezone.utc)
                }
                self.users_collection.insert_one(new_user)
                token = create_access_token({"sub": user_id})
                user_response = {
                    "id": user_id,
                    "name": name,
                    "email": email,
                    "photo_url": photo_url,
                    "grade": None,
                    "board": None,
                    "personalized_response": False
                }
                message = "Google authentication successful"
            
            return {
                "message": message,
                "user": user_response,
                "token": token
            }
        
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e)
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Authentication error: {str(e)}"
            )
