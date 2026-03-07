# VijayeBhav — Device Ownership & Transfer: FastAPI Backend Integration Context

> **Purpose:** This file is a complete implementation guide for GitHub Copilot (or any AI coding assistant) to integrate device ownership, transfer, and lifecycle management into the existing `vijayebhav_v2` FastAPI backend.
>
> **Base URL:** `https://vijayebhav-v2-device-dev-500230722155.asia-south1.run.app/api/v1`  
> **Database:** MongoDB Atlas — `neurosattva`  
> **Auth:** HS256 JWT via `security.py` → `get_current_user()` dependency

---

## 1. Existing Codebase Assumptions

The following already exist and must **not** be replaced — only extended:

| File | Purpose |
|---|---|
| `app/routers/device.py` | Existing device router with `GET /devices/config` and `PATCH /devices/config` |
| `app/controllers/device_config_controller.py` | `DeviceConfigController` — get/upsert device learning config |
| `app/utils/security.py` | `get_current_user()` FastAPI dependency, JWT decode |
| `app/db/database.py` | `get_db()` dependency returning `AsyncIOMotorDatabase` |
| `app/routers/notification.py` | Existing notifications router — do not modify |
| `app/models/` or `app/schemas/` | Existing Pydantic models |

The existing `POST /devices/online/:id` handler in `device.py` uses a simple `find_one_and_update` with `upsert=True` on the `device_config` collection. **This handler must be replaced** with the new ownership-aware version described below.

---

## 2. New MongoDB Collection: `devices`

Create a **new** collection called `devices` in the `neurosattva` database. This is separate from the existing `device_config` collection.

### 2.1 Document Schema

```python
# Conceptual schema — one document per physical device
{
    "_id": str,                    # = device_id (hardware serial / MAC) — PRIMARY KEY
    "device_id": str,              # same as _id, redundant but explicit
    "firmware_version": str,       # e.g. "1.0.3"
    "hardware_revision": str | None,

    # Ownership
    "owner_user_id": str | None,   # FK → users._id  (None = unclaimed)
    "ownership_status": str,       # "unclaimed" | "active" | "transferring"
    "claimed_at": datetime | None,
    "last_provisioned_at": datetime | None,

    # Connectivity
    "is_online": bool,
    "last_seen_at": datetime | None,
    "ip_address": str | None,

    # In-flight transfer window (max 15 min)
    "pending_transfer": {
        "new_user_id": str,
        "initiated_at": datetime,
        "expires_at": datetime,    # initiated_at + 15 minutes — TTL index target
    } | None,

    # Append-only audit trail
    "ownership_history": [
        {
            "user_id": str,
            "claimed_at": datetime,
            "released_at": datetime | None,   # None = current owner
            "release_reason": str | None,     # "transfer" | "manual_unpair" | "admin" | "account_deleted"
            "transfer_to_user": str | None,
        }
    ],

    "created_at": datetime,
    "updated_at": datetime,
}
```

### 2.2 Required MongoDB Indexes

Create these indexes (add to a startup/init function or migration script):

```python
# In app startup or a migration script:

async def create_devices_indexes(db):
    # 1. _id is already the unique primary key
    # 2. Query devices by owner
    await db.devices.create_index("owner_user_id")
    # 3. Efficient active-device queries
    await db.devices.create_index([("owner_user_id", 1), ("ownership_status", 1)])
    # 4. TTL index — auto-expire stuck "transferring" states after 15 min
    await db.devices.create_index(
        "pending_transfer.expires_at",
        expireAfterSeconds=0,
        sparse=True
    )
    # 5. Admin/monitoring queries
    await db.devices.create_index("ownership_status")
    await db.devices.create_index("last_seen_at")
```

---

## 3. New Pydantic Schemas

Add to `app/schemas/device_schemas.py` (create if it doesn't exist, otherwise append):

```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DeviceOnlineRequest(BaseModel):
    firmware_version: str
    hardware_revision: Optional[str] = None


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
    firmware_version: Optional[str] = None
    hardware_revision: Optional[str] = None
    owner_user_id: Optional[str] = None
    ownership_status: str  # "unclaimed" | "active" | "transferring"
    claimed_at: Optional[datetime] = None
    last_provisioned_at: Optional[datetime] = None
    is_online: bool = False
    last_seen_at: Optional[datetime] = None
    ip_address: Optional[str] = None
    pending_transfer: Optional[PendingTransfer] = None
    ownership_history: list[OwnershipHistoryEntry] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
```

---

## 4. New Helper Functions

Add these helpers to `app/controllers/device_config_controller.py` OR create a new file `app/controllers/device_controller.py`:

### 4.1 `_upsert_device_config`

This replaces/extends the existing upsert logic. It must be called after **every** ownership change.

```python
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase


async def _upsert_device_config(db: AsyncIOMotorDatabase, user_id: str, device_id: str, now: datetime):
    """
    Ensure device_config exists for the given user_id.
    Sets device_id and device_online on the config doc.
    On first insert, sets learning_mode/response_type/difficulty_level defaults.
    """
    await db.device_config.find_one_and_update(
        {"user_id": user_id},
        {
            "$set": {
                "device_id": device_id,
                "device_online": True,
                "last_seen_at": now,
                "updated_at": now,
            },
            "$setOnInsert": {
                "user_id": user_id,
                "learning_mode": "Normal",
                "response_type": "Concise",
                "difficulty_level": "Beginner",
                "created_at": now,
            },
        },
        upsert=True,
    )
```

### 4.2 `_notify_user_device_transferred`

Insert a notification for the old owner when their device is transferred.

```python
async def _notify_user_device_transferred(
    db: AsyncIOMotorDatabase,
    old_user_id: str,
    device_id: str,
    new_user_id: str,
):
    """Insert a warning notification for the previous device owner."""
    import uuid
    from datetime import datetime
    now = datetime.utcnow()
    await db.notifications.insert_one({
        "_id": str(uuid.uuid4()),
        "user_id": old_user_id,
        "message": f"Your device {device_id} has been claimed by another user.",
        "type": "warn",
        "created_at": now,
    })
```

---

## 5. Modified & New Router Endpoints

### 5.1 REPLACE existing `POST /devices/online/:device_id`

**File:** `app/routers/device.py`

Find the existing `POST /devices/online/{device_id}` handler and **replace it entirely** with the following. This handler now manages three cases: first-claim, re-claim by same user, and transfer.

```python
from fastapi import APIRouter, Depends, Request, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import uuid

from app.db.database import get_db
from app.utils.security import get_current_user
from app.schemas.device_schemas import DeviceOnlineRequest
from app.controllers.device_controller import (
    _upsert_device_config,
    _notify_user_device_transferred,
)

router = APIRouter()


@router.post("/devices/online/{device_id}")
async def device_online(
    device_id: str,
    request: Request,
    body: DeviceOnlineRequest,
    calling_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Called BY THE DEVICE after every successful WiFi connection.
    Handles three cases atomically:
      CASE 1 — Brand-new device (never registered): claim for this user
      CASE 2 — Same user re-provisioning: update timestamps only
      CASE 3 — Different user provisioning: execute ownership transfer
    """
    now = datetime.utcnow()
    new_user_id = calling_user["_id"]
    client_ip = request.client.host if request.client else None

    existing = await db.devices.find_one(
        {"_id": device_id},
        projection={"owner_user_id": 1, "ownership_status": 1},  # minimal fetch
    )

    # ── CASE 1: Brand-new device ─────────────────────────────────────────
    if existing is None:
        await db.devices.insert_one({
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
        await _upsert_device_config(db, new_user_id, device_id, now)
        return {"status": "claimed", "device_id": device_id}

    # ── CASE 2: Same user re-provisioning ────────────────────────────────
    if existing.get("owner_user_id") == new_user_id:
        await db.devices.update_one(
            {"_id": device_id},
            {"$set": {
                "ownership_status": "active",
                "last_provisioned_at": now,
                "is_online": True,
                "last_seen_at": now,
                "ip_address": client_ip,
                "firmware_version": body.firmware_version,
                "pending_transfer": None,  # cancel any stale transfer
                "updated_at": now,
            }},
        )
        await _upsert_device_config(db, new_user_id, device_id, now)
        return {"status": "re_provisioned", "device_id": device_id}

    # ── CASE 3: Transfer — different user claiming this device ────────────
    old_user_id = existing.get("owner_user_id")

    # Close the previous owner's open history entry
    await db.devices.update_one(
        {"_id": device_id, "ownership_history.released_at": None},
        {"$set": {
            "ownership_history.$.released_at": now,
            "ownership_history.$.release_reason": "transfer",
            "ownership_history.$.transfer_to_user": new_user_id,
        }},
    )

    # Set new owner — cap history array at 20 entries with $slice
    await db.devices.update_one(
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
                    "$slice": -20,  # keep only the last 20 entries
                }
            },
        },
    )

    # Upsert device_config for the new owner
    await _upsert_device_config(db, new_user_id, device_id, now)

    # Notify the old owner (non-fatal — do not let this break the response)
    if old_user_id:
        try:
            await _notify_user_device_transferred(db, old_user_id, device_id, new_user_id)
        except Exception:
            pass  # Notification failure must never block device registration

    return {"status": "transferred", "device_id": device_id}
```

---

### 5.2 NEW: `GET /devices/mine`

Add to `app/routers/device.py`. Returns all active devices owned by the authenticated user.

```python
@router.get("/devices/mine")
async def get_my_devices(
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Returns all devices currently owned by the authenticated user.
    Used by DashboardScreen and SettingsScreen in the Flutter app.
    """
    devices = await db.devices.find(
        {"owner_user_id": user["_id"], "ownership_status": "active"}
    ).to_list(length=50)

    # Convert ObjectId/_id to serialisable form if needed
    for d in devices:
        d["device_id"] = d.get("_id", d.get("device_id"))

    return {"devices": devices}
```

---

### 5.3 NEW: `GET /devices/:device_id/status`

```python
@router.get("/devices/{device_id}/status")
async def get_device_status(
    device_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Returns online status and ownership info for a specific device.
    The requesting user must be the current owner.
    """
    device = await db.devices.find_one({"_id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.get("owner_user_id") != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your device")

    return {
        "device_id": device_id,
        "is_online": device.get("is_online", False),
        "ownership_status": device.get("ownership_status"),
        "last_seen_at": device.get("last_seen_at"),
        "firmware_version": device.get("firmware_version"),
    }
```

---

### 5.4 NEW: `POST /devices/:device_id/unpair`

Allows a user to voluntarily release ownership before physically handing off the device.

```python
@router.post("/devices/{device_id}/unpair")
async def unpair_device(
    device_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Voluntarily releases a user's ownership of a device.
    Sets device to 'unclaimed'. The device continues operating until its JWT expires.
    Also clears device_id from the user's device_config.
    """
    now = datetime.utcnow()

    device = await db.devices.find_one({"_id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.get("owner_user_id") != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your device")

    # Close current open ownership history entry
    await db.devices.update_one(
        {"_id": device_id, "ownership_history.released_at": None},
        {"$set": {
            "ownership_history.$.released_at": now,
            "ownership_history.$.release_reason": "manual_unpair",
        }},
    )

    # Release ownership
    await db.devices.update_one(
        {"_id": device_id},
        {"$set": {
            "owner_user_id": None,
            "ownership_status": "unclaimed",
            "is_online": False,
            "pending_transfer": None,
            "updated_at": now,
        }},
    )

    # Clear device_id from the old owner's device_config
    await db.device_config.update_one(
        {"user_id": user["_id"]},
        {"$set": {
            "device_id": None,
            "device_online": False,
            "updated_at": now,
        }},
    )

    return {"success": True}
```

---

### 5.5 NEW: `GET /devices/:device_id/history`

```python
@router.get("/devices/{device_id}/history")
async def get_device_history(
    device_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Returns the full ownership history for a device.
    Only the current owner can query this.
    """
    device = await db.devices.find_one(
        {"_id": device_id},
        projection={"ownership_history": 1, "owner_user_id": 1},
    )
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.get("owner_user_id") != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your device")

    return {"device_id": device_id, "ownership_history": device.get("ownership_history", [])}
```

---

## 6. Account Deletion — Release Owned Devices

**File:** `app/controllers/user_controller.py` (or wherever `delete_user` / account deletion is handled)

Add the following block **before** deleting the user document. This ensures all owned devices are set to `unclaimed` and their open history entries are closed:

```python
async def release_devices_on_account_deletion(db: AsyncIOMotorDatabase, user_id: str):
    """
    Called during account deletion.
    Releases all devices owned by user_id and closes their history entries.
    """
    now = datetime.utcnow()

    # 1. Set all active devices owned by this user to unclaimed
    await db.devices.update_many(
        {"owner_user_id": user_id, "ownership_status": "active"},
        {"$set": {
            "owner_user_id": None,
            "ownership_status": "unclaimed",
            "is_online": False,
            "updated_at": now,
        }},
    )

    # 2. Close any open ownership_history entries for this user
    await db.devices.update_many(
        {
            "ownership_history.user_id": user_id,
            "ownership_history.released_at": None,
        },
        {"$set": {
            "ownership_history.$.released_at": now,
            "ownership_history.$.release_reason": "account_deleted",
        }},
    )
```

**Call site:** In the `delete_user` handler (e.g. `DELETE /user/me`), add:

```python
await release_devices_on_account_deletion(db, user["_id"])
# ... then proceed with deleting the user document
```

---

## 7. Rate Limiting on `POST /devices/online`

Apply rate limiting to prevent device firmware bugs causing registration floods.

**Option A — Using `slowapi` (recommended if already in the project):**

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/devices/online/{device_id}")
@limiter.limit("5/minute")
async def device_online(request: Request, device_id: str, ...):
    ...
```

**Option B — Simple in-memory per-device rate limit (no Redis required):**

```python
from collections import defaultdict
from datetime import datetime, timedelta
import asyncio

_device_call_times: dict[str, list[datetime]] = defaultdict(list)
_rate_limit_lock = asyncio.Lock()


async def check_device_rate_limit(device_id: str, max_calls: int = 5, window_seconds: int = 60):
    async with _rate_limit_lock:
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=window_seconds)
        # Remove calls outside the window
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
```

Call `await check_device_rate_limit(device_id)` at the top of the `device_online` handler.

> **Note:** For production, replace the in-memory store with Redis to support multi-instance deployments.

---

## 8. Router Registration

Ensure all new endpoints are registered. In `app/main.py` (or `app/api/api.py`):

```python
# Existing line — confirm it includes the device router:
from app.routers import device
app.include_router(device.router, prefix="/api/v1", tags=["devices"])
```

All new endpoints (`/devices/mine`, `/devices/{id}/status`, `/devices/{id}/unpair`, `/devices/{id}/history`) are added to the **same** `device.router`, so no new registration is needed.

---

## 9. Summary of All Changes

| # | Type | Location | Description |
|---|---|---|---|
| 1 | **New collection** | MongoDB `devices` | Ownership ledger — one doc per physical device |
| 2 | **New indexes** | MongoDB | 6 indexes on `devices` including TTL sparse index |
| 3 | **New schemas** | `app/schemas/device_schemas.py` | `DeviceOnlineRequest`, `DeviceModel`, `OwnershipHistoryEntry` |
| 4 | **New helpers** | `app/controllers/device_controller.py` | `_upsert_device_config`, `_notify_user_device_transferred` |
| 5 | **REPLACE handler** | `app/routers/device.py` | `POST /devices/online/:id` — now handles 3-case ownership logic |
| 6 | **New endpoint** | `app/routers/device.py` | `GET /devices/mine` — list user's active devices |
| 7 | **New endpoint** | `app/routers/device.py` | `GET /devices/:id/status` — device online status |
| 8 | **New endpoint** | `app/routers/device.py` | `POST /devices/:id/unpair` — voluntary ownership release |
| 9 | **New endpoint** | `app/routers/device.py` | `GET /devices/:id/history` — ownership audit trail |
| 10 | **Modify** | `app/controllers/user_controller.py` | Call `release_devices_on_account_deletion()` in delete handler |
| 11 | **Add** | `app/routers/device.py` | Rate limit 5 req/min per `device_id` on `/devices/online` |

---

## 10. What Does NOT Change

- `GET /devices/config` — unchanged
- `PATCH /devices/config` — unchanged
- `device_config` collection schema — only gains `device_id` and `device_online` fields (already set by `_upsert_device_config`)
- BLE provisioning protocol — no firmware or mobile app BLE changes needed
- Auth flow, JWT logic, Firebase integration — untouched
- Notifications collection — new transfer notifications are **inserted** (no schema change)
- All other routers (`auth`, `user`, `conversation`, `message`, `agent`, `notification`) — untouched

---

## 11. Key Behavioural Rules for Copilot

1. **`_id` of a `devices` doc = `device_id`** (hardware serial/MAC string), not a generated ObjectId.
2. **`POST /devices/online` is idempotent for same-user** — calling it multiple times only updates `last_seen_at`. No duplicate `ownership_history` entries are created in CASE 2.
3. **Transfer notification failure must never block the device registration response** — wrap `_notify_user_device_transferred` in a `try/except`.
4. **`ownership_history` is append-only** — no endpoint deletes or modifies history entries directly; only `released_at` is set via `$set` on the matched array element.
5. **`$slice: -20`** must be applied on every `$push` to `ownership_history` to prevent unbounded array growth.
6. **`device_config` is user-scoped, `devices` is device-scoped** — they are NOT the same collection and must both be updated on ownership changes.
7. **401 from `/devices/online` causes the ESP32 FSM to transition to `BLE_CONFIG`** — ensure `get_current_user()` dependency returns 401 (not 500) on expired/invalid JWT.