from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

class DeviceStatus(BaseModel):
    device_id: str
    status: str

router = APIRouter(prefix="/devices", tags=["Device"])


@router.post("/online/{device_id}")
async def device_online(device_id: str, request: DeviceStatus):
    print(request.status)
    return {"message": "Device online"}