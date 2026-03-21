import asyncio
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.agents.core_agent import run_agent
from app.utility.security import get_current_user
from app.models.user import User
import tempfile
from app.agents.utility import client, translate_text, generate_full_audio
from app.agents.agent_memory_controller import get_or_create_device_session_id
import os
import logging

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
    # 1. Receive user audio
    wav_data = await request.body()

    # 2. Speech-to-text + language detection
    with tempfile.NamedTemporaryFile(delete=True, suffix=".wav") as temp_audio:
        temp_audio.write(wav_data)
        temp_audio.flush()
        result = client.speech_to_text.translate(
            file=temp_audio,
            model="saaras:v2.5"
        )

    language_code = result.language_code if result.language_code else ""

    # Unsupported / unrecognised language guard
    if not language_code or language_code not in SUPPORTED_LANGUAGE_CODES:
        logger.warning(f"Unsupported or unrecognised language code: '{language_code}'")
        error_audio = await generate_full_audio(UNSUPPORTED_LANGUAGE_MESSAGE, language_code="en-IN")
        return StreamingResponse(
            iter([error_audio]),
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
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

    # 5. Generate full TTS audio at once
    audio_bytes = await generate_full_audio(response, language_code=language_code)

    # 6. Stream audio chunks back (cancellable)
    async def audio_chunk_generator():
        for i in range(0, len(audio_bytes), STREAM_CHUNK_SIZE):
            if cancel_event.is_set():
                logger.info("Stream cancelled — new request preempted this one.")
                break
            yield audio_bytes[i:i + STREAM_CHUNK_SIZE]

    return StreamingResponse(
        audio_chunk_generator(),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Length": str(len(audio_bytes)),
        },
    )