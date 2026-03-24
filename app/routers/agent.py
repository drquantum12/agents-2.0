import asyncio
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.agents.core_agent import run_agent
from app.utility.security import get_current_user
from app.models.user import User
import tempfile
from app.agents.utility import translate_text, streaming_audio_response
from app.agents.agent_memory_controller import get_or_create_device_session_id
import os
from typing import AsyncGenerator
import logging
from app.state import state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["Agent"])
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# Language codes supported by Sarvam bulbul:v2 TTS + saaras:v2.5 STT
SUPPORTED_LANGUAGE_CODES = {
    "en-IN",  # English
    "hi-IN",  # Hindi
    "bn-IN",  # Bengali
    "gu-IN",  # Gujarati
    "kn-IN",  # Kannada
    "ml-IN",  # Malayalam
    "mr-IN",  # Marathi
    "od-IN",  # Odia
    "pa-IN",  # Punjabi
    "ta-IN",  # Tamil
    "te-IN",  # Telugu
}

UNSUPPORTED_LANGUAGE_MESSAGE = (
    "I am sorry, I was not able to recognize your language. "
    "Please try speaking in one of the supported languages: "
    "English, Hindi, Bengali, Gujarati, Kannada, Malayalam, Marathi, Odia, Punjabi, Tamil, or Telugu."
)

STREAM_CHUNK_SIZE = 32 * 1024  # 32 KB chunks for streaming

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
    
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    }
    # 1. Receive user audio
    wav_data = await request.body()

    # with open("app/data/input_32bit.wav", "wb") as f:
    #         f.write(wav_data)

    # 2. Speech-to-text + language detection
    with tempfile.NamedTemporaryFile(delete=True, suffix=".wav") as temp_audio:
        temp_audio.write(wav_data)
        temp_audio.flush()
        result = state.sarvam_client.speech_to_text.translate(
            file=temp_audio,
            model="saaras:v2.5"
        )

    language_code = result.language_code if result.language_code else ""

    # Unsupported / unrecognised language guard
    if not language_code or language_code not in SUPPORTED_LANGUAGE_CODES:
        logger.warning(f"Unsupported or unrecognised language code: '{language_code}'")
        return StreamingResponse(
            streaming_audio_response(UNSUPPORTED_LANGUAGE_MESSAGE, language_code="en-IN"),
            media_type="audio/mpeg",
            headers=headers,
        )

    # --- Interruption logic ---
    user_id = str(user["_id"])
    previous_event = _active_cancel_events.get(user_id)
    if previous_event:
        previous_event.set()

    cancel_event = asyncio.Event()
    _active_cancel_events[user_id] = cancel_event
    # --------------------------

    # 3. Get LLM response
    session_id = get_or_create_device_session_id(user_id=user["_id"])
    response = await asyncio.to_thread(run_agent, user=user, query=result.transcript, session_id=session_id)

    # 4. Translate back to detected language
    if language_code != "en-IN":
        response = await asyncio.to_thread(
            translate_text, response,
            "en-IN",
            language_code,
        )

    return StreamingResponse(
        _cancellable_stream(streaming_audio_response(response, language_code=language_code), cancel_event),
        media_type="audio/mpeg",
        headers=headers,
    )