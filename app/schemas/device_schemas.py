from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class DeviceOnlineRequest(BaseModel):
    firmware_version: float = 0.0
    hardware_revision: Optional[float] = None


class OwnershipHistoryEntry(BaseModel):
    user_id: str
    claimed_at: datetime
    released_at: Optional[datetime] = None
    release_reason: Optional[str] = None
    transfer_to_user: Optional[str] = None


class PendingTransfer(BaseModel):
    new_user_id: str
    initiated_at: datetime
    expires_at: datetime


class DeviceModel(BaseModel):
    device_id: str
    firmware_version: Optional[float] = None
    hardware_revision: Optional[float] = None
    owner_user_id: Optional[str] = None
    ownership_status: str  # "unclaimed" | "active" | "transferring"
    claimed_at: Optional[datetime] = None
    last_provisioned_at: Optional[datetime] = None
    is_online: bool = False
    last_seen_at: Optional[datetime] = None
    ip_address: Optional[str] = None
    pending_transfer: Optional[PendingTransfer] = None
    ownership_history: List[OwnershipHistoryEntry] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
