from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status
import os
import logging

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60  # 30 days

# When ENABLE_AUTH=false (any casing), every protected endpoint receives a
# stub user and no token is required. Intended for local testing only.
ENABLE_AUTH: bool = os.getenv("ENABLE_AUTH", "true").strip().lower() != "false"

if not ENABLE_AUTH:
    logger.warning(
        "ENABLE_AUTH=false — authentication is DISABLED. "
        "All protected endpoints will use a stub test user. "
        "Never run this in production."
    )

# Stub returned when auth is disabled. Matches the UserSchema field set so that
# endpoint code that reads user["_id"], user.get("grade"), etc. won't break.
_DEV_STUB_USER = {
                "_id": "ptLFqq0N9JTyYL7lkAqhB1YSFj32",
                "name": "ARJUN SINGH TOMAR",
                "email": "arjunsinghtomar03511@gmail.com",
                "created_at": {
                    "$date": "2025-07-27T09:08:21.759Z"
                },
                "photo_url": "https://lh3.googleusercontent.com/a/ACg8ocIQgd6aG3SosJ5oHAk3MSQpe3c71QTgpac65fkC-fV4EcGFn66e=s96-c",
                "grade": "11",
                "personalized_response": True,
                "board": "ICSE",
                "last_quiz_submission_time": {
                    "$date": "2025-09-20T22:01:04.197Z"
                },
                "last_active": {
                    "$date": "2025-09-25T06:17:59.535Z"
                },
                "last_streak_date": {
                    "$date": "2025-09-20T00:00:00.000Z"
                },
                "streak_count": 1,
                "subscription": {
                    "status": "free",
                    "expiry": None,
                    "practice_test": 0,
                    "query": 0,
                    "quiz": 0
                },
                "updated_at": {
                    "$date": "2026-03-06T14:00:27.775Z"
                }
                }

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# When auth is enabled the scheme raises 401 automatically for missing tokens.
# When auth is disabled we use auto_error=False so requests without an
# Authorization header are not rejected before reaching get_current_user.
_TOKEN_URL = "/api/v1/auth/login"
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=_TOKEN_URL,
    auto_error=ENABLE_AUTH,
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta
        else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


from app.db_utility.mongo_db import mongo_db


async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)):
    # ── Auth disabled: return stub user immediately ──────────────────────────
    if not ENABLE_AUTH:
        return _DEV_STUB_USER

    # ── Auth enabled: full token validation ─────────────────────────────────
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id: str = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    user = mongo_db["users"].find_one({"_id": user_id})
    if user is None:
        raise credentials_exception

    return user
