"""
agents/nudge.py
─────────────────────────────────────────────
Event-driven nudge delivery via MQTT — zero polling, no extra WS connection.

How it works
────────────
  • When set_reminder / spaced_repeat tools create a MongoDB record they
    immediately call schedule_nudge(), which creates an asyncio Task that
    sleeps until fire_at then publishes the payload to the device via MQTT.

  • recover_pending_nudges() is called once at startup to reschedule any
    tasks that were in flight when the server last restarted.  It also
    checks for active lessons that have been idle ≥ 4 hours and publishes
    a lesson_resume nudge immediately.

  • _push_nudge() looks up the device_id for the user and publishes JSON to
    the MQTT topic  devices/{device_id}/nudge  (QoS 1).
    The device's mqtt_service.c subscribes to this topic on connect and
    calls display_text() with the extracted message.

  • No polling loop, no APScheduler, no Redis — pure asyncio.sleep().
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.db_utility.mongo_db import mongo_db
from app.state import state

logger = logging.getLogger(__name__)

# Reference to the main event loop — set once at startup
_event_loop: Optional[asyncio.AbstractEventLoop] = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _event_loop
    _event_loop = loop


# ── Device lookup ─────────────────────────────────────────────────────────────

def _get_device_id(user_id: str) -> Optional[str]:
    """Return the device_id (_id) owned by user_id, or None if not found."""
    doc = mongo_db["devices"].find_one({"owner_user_id": user_id}, {"_id": 1})
    if not doc:
        logger.info("nudge: no device found for user=%s", user_id[:12])
        return None
    return str(doc["_id"])


# ── Push helpers ──────────────────────────────────────────────────────────────

async def _push_nudge(user_id: str, payload: dict) -> bool:
    """
    Publish a JSON nudge to  devices/{device_id}/nudge  via MQTT (QoS 1).
    Returns True if published, False if the device has no registered device_id
    or the MQTT client is unavailable.
    """
    device_id = await asyncio.to_thread(_get_device_id, user_id)
    if not device_id:
        return False

    mqtt = state.mqtt_client
    if mqtt is None:
        logger.warning("nudge: MQTT client not ready — cannot push to user=%s", user_id[:12])
        return False

    topic = f"devices/{device_id}/nudge"
    message = json.dumps(payload, separators=(',', ':'))
    try:
        await asyncio.to_thread(mqtt.publish, topic, message, 1)
        logger.info(
            "nudge: published type=%s to %s (user=%s)",
            payload.get("type"), topic, user_id[:12],
        )
        return True
    except Exception as exc:
        logger.warning("nudge: MQTT publish failed for user=%s: %s", user_id[:12], exc)
        return False


# ── Scheduled delivery coroutine ─────────────────────────────────────────────

async def _deliver_at(
    fire_at:    datetime,
    user_id:    str,
    payload:    dict,
    collection: str,
    record_id,
) -> None:
    """
    Sleep until fire_at, publish payload to device via MQTT, mark MongoDB
    record delivered.  If fire_at is in the past (e.g. server-restart
    recovery) the sleep is skipped via max(delay, 0).
    """
    # PyMongo returns naive datetimes by default — normalise to UTC-aware
    # before subtracting so we don't get "can't subtract offset-naive and
    # offset-aware datetimes" when fire_at has no tzinfo attached.
    if fire_at.tzinfo is None:
        fire_at = fire_at.replace(tzinfo=timezone.utc)
    delay = (fire_at - datetime.now(tz=timezone.utc)).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)

    delivered = await _push_nudge(user_id, payload)
    if delivered:
        try:
            await asyncio.to_thread(
                mongo_db[collection].update_one,
                {"_id": record_id},
                {"$set": {"delivered": True}},
            )
        except Exception as exc:
            logger.error(
                "nudge: failed to mark delivered (col=%s id=%s): %s",
                collection, record_id, exc,
            )


# ── Sync scheduler — called from tool threads ─────────────────────────────────

def schedule_nudge(
    user_id:    str,
    fire_at:    datetime,
    payload:    dict,
    collection: str,
    record_id,
) -> None:
    """
    Schedule a nudge from a synchronous LangChain tool thread.
    Uses asyncio.run_coroutine_threadsafe to post the Task onto the main loop.
    Call this immediately after writing to MongoDB — no polling needed.
    """
    if _event_loop is None or _event_loop.is_closed():
        logger.warning(
            "nudge: event loop not ready — cannot schedule nudge for user=%s", user_id[:12]
        )
        return
    asyncio.run_coroutine_threadsafe(
        _deliver_at(fire_at, user_id, payload, collection, record_id),
        _event_loop,
    )
    logger.info(
        "nudge: scheduled type=%s for user=%s at %s",
        payload.get("type"), user_id[:12], fire_at.isoformat(),
    )


# ── Startup recovery ──────────────────────────────────────────────────────────

async def recover_pending_nudges() -> None:
    """
    Reschedule any undelivered nudges from before the last server restart.
    Called once during app lifespan startup, after the event loop is running.
    Past-due nudges (fire_at already elapsed) are scheduled with delay=0
    and will fire as soon as the MQTT client is ready.

    Also checks for active lessons idle ≥ 4 hours and immediately publishes
    a lesson_resume nudge so the device shows a prompt on next boot.
    """
    now   = datetime.now(tz=timezone.utc)
    count = 0

    for doc in mongo_db["reminders"].find({"delivered": False}):
        asyncio.create_task(
            _deliver_at(
                doc["fire_at"],
                doc["user_id"],
                {"type": "nudge", "message": doc["message"]},
                "reminders",
                doc["_id"],
            )
        )
        count += 1

    for doc in mongo_db["spaced_reviews"].find({"delivered": False}):
        topic = doc.get("topic", "a topic")
        days  = doc.get("interval_days", 1)
        msg   = (
            f"Time to review '{topic}'! "
            f"It's been {days} day{'s' if days != 1 else ''} — "
            f"a quick recap will lock it into long-term memory."
        )
        asyncio.create_task(
            _deliver_at(
                doc["review_at"],
                doc["user_id"],
                {"type": "nudge", "message": msg},
                "spaced_reviews",
                doc["_id"],
            )
        )
        count += 1

    logger.info("nudge: rescheduled %d pending nudges after restart", count)

    # ── Lesson-idle check ──────────────────────────────────────────────────
    # For each user with an active lesson idle ≥ 4 hours, push a
    # lesson_resume nudge immediately (delay=0 in _deliver_at).
    try:
        lesson_count = 0
        for tm_doc in mongo_db["teacher_memory"].find({"lesson_status": "ON"}):
            last_lesson = tm_doc.get("last_lesson_at")
            if not last_lesson:
                continue
            if last_lesson.tzinfo is None:
                last_lesson = last_lesson.replace(tzinfo=timezone.utc)
            idle_hours = (now - last_lesson).total_seconds() / 3600
            if idle_hours < 4:
                continue

            user_id  = tm_doc.get("user_id", "")
            plan     = tm_doc.get("lesson_plan") or []
            idx      = tm_doc.get("subtopic_idx", 0)
            topic    = tm_doc.get("topic", "your lesson")
            subtopic = tm_doc.get("current_subtopic", "where you left off")
            message  = (
                f"Welcome back! We were on subtopic {idx + 1} of {len(plan)} "
                f"in '{topic}': {subtopic}. "
                f"Press the button when you're ready to continue."
            )
            asyncio.create_task(
                _push_nudge(user_id, {
                    "type":     "lesson_resume",
                    "topic":    topic,
                    "subtopic": subtopic,
                    "current":  idx + 1,
                    "total":    len(plan),
                    "message":  message,
                })
            )
            lesson_count += 1

        if lesson_count:
            logger.info("nudge: sent lesson_resume to %d idle-lesson users", lesson_count)
    except Exception as exc:
        logger.warning("nudge: lesson-idle check failed: %s", exc)
