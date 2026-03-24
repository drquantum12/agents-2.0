from fastapi import APIRouter, status
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.controllers.auth_controller import AuthController
from app.models.user import UserRegister

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Initialize controller
auth_controller = AuthController()

# Request/Response Models
class UserLogin(BaseModel):
    id_token: str

class GoogleAuth(BaseModel):
    id_token: str

class UserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    photo_url: Optional[str] = None
    grade: Optional[str] = None
    board: Optional[str] = None
    personalized_response: bool = False

class AuthResponse(BaseModel):
    message: str
    user: UserResponse
    token: str

# Endpoints

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister):
    """Register a new user via Firebase ID token"""
    return await auth_controller.register_user(user_data)

@router.post("/login", response_model=AuthResponse)
async def login(login_data: UserLogin):
    """Login with email and password via Firebase ID token"""
    return await auth_controller.login_user(login_data.id_token)

@router.post("/google", response_model=AuthResponse)
async def google_auth(auth_data: GoogleAuth):
    """Authenticate or register user with Google Sign-In"""
    return await auth_controller.google_auth(auth_data.id_token)
