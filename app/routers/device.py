from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.utility.security import get_current_user
from app.controllers.device_config_controller import DeviceConfigController


class DeviceStatus(BaseModel):
    device_id: str
    status: str


class DeviceConfigResponse(BaseModel):
    id: str
    user_id: str
    learning_mode: str
    response_type: str
    difficulty_level: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DeviceConfigUpdate(BaseModel):
    learning_mode: Optional[str] = None  # Strict | Normal
    response_type: Optional[str] = None  # Detailed | Concise
    difficulty_level: Optional[str] = None  # Beginner | Intermediate | Advanced


router = APIRouter(prefix="/devices", tags=["Device"])

# Initialize controller
device_config_controller = DeviceConfigController()


@router.post("/online/{device_id}")
async def device_online(device_id: str, request: DeviceStatus):
    print(request.status)
    return {"message": "Device online"}


@router.get("/config", response_model=DeviceConfigResponse)
async def get_device_config(current_user: dict = Depends(get_current_user)):
    """Get device configuration for the current user"""
    return await device_config_controller.get_device_config(current_user["_id"])


@router.patch("/config", response_model=DeviceConfigResponse)
async def update_device_config(
    update_data: DeviceConfigUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Partially update device configuration for the current user"""
    fields = update_data.model_dump(exclude_unset=True, exclude_none=True)
    return await device_config_controller.update_device_config(current_user["_id"], fields)