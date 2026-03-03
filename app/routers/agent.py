import asyncio
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.agents.core_agent import run_agent, pick_filler_phrase
from app.utility.security import get_current_user
from app.models.user import User
import tempfile
from app.agents.utility import client, translate_text, sentence_pipelined_tts, generate_filler_audio
from app.agents.agent_memory_controller import get_or_create_device_session_id
from typing import AsyncGenerator
import os
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["Agent"])
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# Tracks the active cancellation event per user so a new request can interrupt the current stream.
_active_cancel_events: dict[str, asyncio.Event] = {}


async def _cancellable_stream(
    generator: AsyncGenerator[bytes, None],
    cancel_event: asyncio.Event,
) -> AsyncGenerator[bytes, None]:
    """Wraps an async byte generator and stops yielding once cancel_event is set."""
    async for chunk in generator:
        if cancel_event.is_set():
            logger.info("Stream cancelled — new request preempted this one.")
            break
        yield chunk


class QueryRequest(BaseModel):
    query: str
        
@router.post("/query")
async def agent(request: QueryRequest, user: User = Depends(get_current_user)):
    session_id = get_or_create_device_session_id(user_id=user["_id"])
    response = await asyncio.to_thread(run_agent, user=user, query=request.query, session_id=session_id)
    return {"response": response}
        
@router.post("/device-voice-assistant")
async def device_voice_assistant(request: Request,
                                  user: User = Depends(get_current_user)
                                  ):
    wav_data = await request.body()

    with open("app/data/input_32bit.wav", "wb") as f:
            f.write(wav_data)
    
    with tempfile.NamedTemporaryFile(delete=True, suffix=".wav") as temp_audio:
            temp_audio.write(wav_data)
            temp_audio.flush()
            result = client.speech_to_text.translate(
            file=temp_audio,
            model="saaras:v2.5"
        )
    
    session_id = get_or_create_device_session_id(user_id=user["_id"])
    language_code = result.language_code if result.language_code else "en-IN"

    # --- Interruption logic ---
    # Cancel any in-flight stream for this user before starting a new one.
    user_id = str(user["_id"])
    previous_event = _active_cancel_events.get(user_id)
    if previous_event:
        previous_event.set()

    cancel_event = asyncio.Event()
    _active_cancel_events[user_id] = cancel_event
    # --------------------------

    agent_task = asyncio.create_task(asyncio.to_thread(run_agent, user=user, query=result.transcript, session_id=session_id))

    response = await agent_task

    headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    
    return StreamingResponse(
        _cancellable_stream(sentence_pipelined_tts(response, language_code=language_code), cancel_event),
        media_type="audio/mpeg",
        headers=headers
    )