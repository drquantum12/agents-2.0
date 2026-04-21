import os
import tempfile
from fastapi import APIRouter, BackgroundTasks, Depends, Request, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import asyncio
from bson import Decimal128


def _d128_to_float(value):
    """Convert a bson.Decimal128 to float; pass through other types unchanged."""
    if isinstance(value, Decimal128):
        return float(value.to_decimal())
    return value


def _sanitize_doc(doc):
    """Recursively convert BSON types (e.g. Decimal128) in a MongoDB document to JSON-safe types."""
    if isinstance(doc, dict):
        return {k: _sanitize_doc(v) for k, v in doc.items()}
    if isinstance(doc, list):
        return [_sanitize_doc(v) for v in doc]
    if isinstance(doc, Decimal128):
        return float(doc.to_decimal())
    return doc

from app.utility.security import get_current_user
from app.controllers.device_config_controller import DeviceConfigController
from app.controllers.device_controller import (
    _upsert_device_config,
    _notify_user_device_transferred,
)
from app.schemas.device_schemas import DeviceOnlineRequest
from app.db_utility.mongo_db import mongo_db
from app.state import state
from google.cloud import storage

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

# ─── Rate Limiting ─────────────────────────────────────────────────────────────
_device_call_times: dict[str, list[datetime]] = defaultdict(list)
_rate_limit_lock = asyncio.Lock()


async def _check_device_rate_limit(
    device_id: str, max_calls: int = 5, window_seconds: int = 60
) -> None:
    async with _rate_limit_lock:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_seconds)
        _device_call_times[device_id] = [
            t for t in _device_call_times[device_id] if t > cutoff
        ]
        if len(_device_call_times[device_id]) >= max_calls:
            raise HTTPException(
                status_code=429,
                detail="Too many requests",
                headers={"Retry-After": "60"},
            )
        _device_call_times[device_id].append(now)


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/online/{device_id}")
async def device_online(
    device_id: str,
    request: Request,
    body: DeviceOnlineRequest,
    calling_user: dict = Depends(get_current_user),
):
    """
    Called BY THE DEVICE after every successful WiFi connection.
    Handles three cases:
      CASE 1 — Brand-new device (never registered): claim for this user
      CASE 2 — Same user re-provisioning: update timestamps only
      CASE 3 — Different user provisioning: execute ownership transfer
    """
    await _check_device_rate_limit(device_id)

    now = datetime.now(timezone.utc)
    new_user_id = calling_user["_id"]
    client_ip = request.client.host if request.client else None

    existing = mongo_db["devices"].find_one(
        {"_id": device_id},
        projection={"owner_user_id": 1, "ownership_status": 1},
    )

    # ── CASE 1: Brand-new device ─────────────────────────────────────────
    if existing is None:
        mongo_db["devices"].insert_one({
            "_id": device_id,
            "device_id": device_id,
            "firmware_version": body.firmware_version,
            "hardware_revision": body.hardware_revision,
            "owner_user_id": new_user_id,
            "ownership_status": "active",
            "claimed_at": now,
            "last_provisioned_at": now,
            "is_online": True,
            "last_seen_at": now,
            "ip_address": client_ip,
            "pending_transfer": None,
            "ownership_history": [{
                "user_id": new_user_id,
                "claimed_at": now,
                "released_at": None,
                "release_reason": None,
                "transfer_to_user": None,
            }],
            "created_at": now,
            "updated_at": now,
        })
        _upsert_device_config(new_user_id, device_id, now)
        return {"status": "claimed", "device_id": device_id}

    # ── CASE 2: Same user re-provisioning ────────────────────────────────
    if existing.get("owner_user_id") == new_user_id:
        mongo_db["devices"].update_one(
            {"_id": device_id},
            {"$set": {
                "ownership_status": "active",
                "last_provisioned_at": now,
                "is_online": True,
                "last_seen_at": now,
                "ip_address": client_ip,
                "firmware_version": body.firmware_version,
                "pending_transfer": None,
                "updated_at": now,
            }},
        )
        _upsert_device_config(new_user_id, device_id, now)
        return {"status": "re_provisioned", "device_id": device_id}

    # ── CASE 3: Transfer — different user claiming this device ────────────
    old_user_id = existing.get("owner_user_id")

    # Close the previous owner's open history entry
    mongo_db["devices"].update_one(
        {"_id": device_id, "ownership_history.released_at": None},
        {"$set": {
            "ownership_history.$.released_at": now,
            "ownership_history.$.release_reason": "transfer",
            "ownership_history.$.transfer_to_user": new_user_id,
        }},
    )

    # Set new owner — cap history array at 20 entries with $slice
    mongo_db["devices"].update_one(
        {"_id": device_id},
        {
            "$set": {
                "owner_user_id": new_user_id,
                "ownership_status": "active",
                "claimed_at": now,
                "last_provisioned_at": now,
                "is_online": True,
                "last_seen_at": now,
                "ip_address": client_ip,
                "firmware_version": body.firmware_version,
                "pending_transfer": None,
                "updated_at": now,
            },
            "$push": {
                "ownership_history": {
                    "$each": [{
                        "user_id": new_user_id,
                        "claimed_at": now,
                        "released_at": None,
                        "release_reason": None,
                        "transfer_to_user": None,
                    }],
                    "$slice": -20,
                }
            },
        },
    )

    _upsert_device_config(new_user_id, device_id, now)

    # Notify old owner — failure must never block the device registration response
    if old_user_id:
        try:
            _notify_user_device_transferred(old_user_id, device_id, new_user_id)
        except Exception:
            pass

    return {"status": "transferred", "device_id": device_id}

# for capturing device hearbeats
@router.post("/heartbeat/{device_id}")
async def device_heartbeat(
    device_id: str,
    request: Request,
    calling_user: dict = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    client_ip = request.client.host if request.client else None

    result = mongo_db["devices"].update_one(
        {"_id": device_id, "owner_user_id": calling_user["_id"]},
        {"$set": {
            "last_seen_at": now,
            "ip_address": client_ip,
            "is_online": True,
            "updated_at": now,
        }},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Device not found or not owned by you")

    return Response(status_code=204)

@router.get("/mine")
async def get_my_devices(
    user: dict = Depends(get_current_user),
):
    """Returns all devices currently owned by the authenticated user."""
    devices = list(
        mongo_db["devices"]
        .find({"owner_user_id": user["_id"], "ownership_status": "active"})
        .limit(50)
    )
    sanitized = []
    for d in devices:
        d["device_id"] = d.get("_id", d.get("device_id"))
        sanitized.append(_sanitize_doc(d))
    return {"devices": sanitized}


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


@router.get("/{device_id}/status")
async def get_device_status(
    device_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Returns online status and ownership info for a specific device.
    The requesting user must be the current owner.
    """
    device = mongo_db["devices"].find_one({"_id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.get("owner_user_id") != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your device")

    return {
        "device_id": device_id,
        "is_online": device.get("is_online", False),
        "ownership_status": device.get("ownership_status"),
        "last_seen_at": device.get("last_seen_at"),
        "firmware_version": _d128_to_float(device.get("firmware_version")),
    }


@router.post("/{device_id}/unpair")
async def unpair_device(
    device_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Voluntarily releases a user's ownership of a device.
    Sets device to 'unclaimed'. Also clears device_id from the user's device_config.
    """
    now = datetime.now(timezone.utc)

    device = mongo_db["devices"].find_one({"_id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.get("owner_user_id") != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your device")

    # Close current open ownership history entry
    mongo_db["devices"].update_one(
        {"_id": device_id, "ownership_history.released_at": None},
        {"$set": {
            "ownership_history.$.released_at": now,
            "ownership_history.$.release_reason": "manual_unpair",
        }},
    )

    # Release ownership
    mongo_db["devices"].update_one(
        {"_id": device_id},
        {"$set": {
            "owner_user_id": None,
            "ownership_status": "unclaimed",
            "is_online": False,
            "pending_transfer": None,
            "updated_at": now,
        }},
    )

    # Clear device reference from the user's device_config
    mongo_db["device_config"].update_one(
        {"user_id": user["_id"]},
        {"$set": {
            "device_id": None,
            "device_online": False,
            "updated_at": now,
        }},
    )

    # send unpair notification to device via MQTT
    topic = f"devices/{device_id}/commands"
    message = "unpair"
    try:
        state.mqtt_client.publish(topic, message, qos=1)
    except Exception:
        pass  # Log error if needed, but don't fail the unpairing process

    return {"success": True}


@router.get("/{device_id}/history")
async def get_device_history(
    device_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Returns the full ownership history for a device.
    Only the current owner can query this.
    """
    device = mongo_db["devices"].find_one(
        {"_id": device_id},
        projection={"ownership_history": 1, "owner_user_id": 1},
    )
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.get("owner_user_id") != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your device")

    return {
        "device_id": device_id,
        "ownership_history": device.get("ownership_history", []),
    }

# endpoint to return latest firmware binary from google cloud storage as octet-stream for the device to download and update itself
@router.get("/firmware/download")
async def download_firmware(background_tasks: BackgroundTasks):
    """
    Returns the latest firmware binary from Google Cloud Storage.
    The device can call this endpoint to download the firmware for updates.
    """
    bucket_name = "vijayebhav-firmware"

    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        latest_firmware_version = mongo_db["firmware"].find_one(
            sort=[("version", -1)],
            projection={"version": 1},
        )
        if not latest_firmware_version:
            raise HTTPException(status_code=404, detail="No firmware versions found")

        blob_name = f"firmware_v{_d128_to_float(latest_firmware_version['version'])}.bin"
        blob = bucket.blob(blob_name)
        if not blob.exists():
            raise HTTPException(status_code=404, detail="Firmware not found")

        # Download to a temp file so FileResponse can handle Content-Length automatically
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        try:
            blob.download_to_file(tmp)
            tmp.close()
        except Exception:
            tmp.close()
            os.unlink(tmp.name)
            raise

        # Clean up the temp file after the response is fully sent
        background_tasks.add_task(os.unlink, tmp.name)

        return FileResponse(
            path=tmp.name,
            media_type="application/octet-stream",
            filename=blob_name,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading firmware: {str(e)}")