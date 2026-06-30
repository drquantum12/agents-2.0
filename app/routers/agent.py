import asyncio
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.agents import chat
from app.utility.security import get_current_user, decode_access_token
from app.models.user import User
import tempfile
from app.agents.utility import translate_text, streaming_audio_response, test_audio_stream, test_audio_stream_with_jitter
from app.db_utility.mongo_db import mongo_db, get_or_create_device_session_id
from app.utility.security import ENABLE_AUTH, _DEV_STUB_USER
import os, io
from typing import AsyncGenerator, Callable, Optional
import logging
from app.state import state

import numpy as np

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
async def agent(request: QueryRequest, 
                user: User = Depends(get_current_user)
                ):
    session_id, is_new_session = get_or_create_device_session_id(user_id=user["_id"])
    response = await asyncio.to_thread(chat, user_id=str(user["_id"]), session_id=session_id, query=request.query, is_new_session=is_new_session)
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

    # return
    # return StreamingResponse(
    #     test_audio_stream(),
    #     media_type="audio/mpeg",
    #     headers=headers
    # )

    # 2. Speech-to-text + language detection (off-thread — sync client blocks otherwise)
    result = await asyncio.to_thread(
        lambda: state.sarvam_client.speech_to_text.translate(
            file=wav_data,
            model="saaras:v2.5",
        )
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
    
    # print(f"Detected language code: {language_code}")
    # print(f"Transcript: {result.transcript}")
    # return StreamingResponse(
    #     test_audio_stream(),
    #     media_type="audio/mpeg",
    #     headers=headers
    # )

    # --- Interruption logic ---
    user_id = str(user["_id"])
    previous_event = _active_cancel_events.get(user_id)
    if previous_event:
        previous_event.set()

    cancel_event = asyncio.Event()
    _active_cancel_events[user_id] = cancel_event
    # --------------------------

    # 3. Get LLM response
    session_id, is_new_session = get_or_create_device_session_id(user_id=user["_id"])
    response = await asyncio.to_thread(chat, user_id=str(user["_id"]),
                                    session_id=session_id, 
                                    query=result.transcript,
                                    is_new_session=is_new_session,
                                    grade=user.get("grade"),
                                    board=user.get("board"),
                                    personalized=user.get("personalized", False)
                                    )

    # 4. Translate back to detected language
    if language_code != "en-IN":
        response = await asyncio.to_thread(
            translate_text, response,
            "en-IN",
            language_code,
        )

    return StreamingResponse(
        _cancellable_stream(streaming_audio_response(response, language_code=language_code, output_audio_bitrate="8k"), cancel_event),
        media_type="audio/mpeg",
        headers=headers,
    )

# simulating audio chunks stream with random network jitters
@router.post("/device-voice-assistant-test")
async def device_voice_assistant_test(request: Request):
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    }
    # wav_data = await request.body()

    # with open("app/data/input_32bit_test.wav", "wb") as f:
    #         f.write(wav_data)
            
    return StreamingResponse(
        test_audio_stream(),
        media_type="audio/mpeg",
        headers=headers
    )

@router.websocket("/device-voice-assistant-ws-test")
async def device_voice_assistant_ws_test(websocket: WebSocket):
    """
    WebSocket test endpoint — no auth, no STT/LLM/TTS calls.

    Protocol:
      Device → Server : binary frame — raw audio bytes (ignored, just consumed)
      Server → Device : binary frames — chunks of app/data/sample.mp3 streamed back
      Server → Device : text "DONE" — finished streaming the test audio

    Lets a device test its WebSocket audio streaming pipeline against a
    canned response without touching any real STT/LLM/TTS services.
    """
    await websocket.accept()
    logger.info("[WS-TEST] Device connected")

    try:
        while True:
            await websocket.receive_bytes()

            async for chunk in test_audio_stream():
                await websocket.send_bytes(chunk)

            await websocket.send_text("DONE")

    except WebSocketDisconnect:
        logger.info("[WS-TEST] Device disconnected")
    except Exception as e:
        logger.error(f"[WS-TEST] Unexpected error: {e}")
        try:
            await websocket.send_text(f"ERROR:{e}")
        except Exception:
            pass


@router.websocket("/device-voice-assistant-ws")
async def device_voice_assistant_ws(websocket: WebSocket, token: str):
    """
    WebSocket endpoint for the AI device voice assistant.

    Protocol:
      Device  → Server : binary frame  — raw WAV audio bytes
      Server  → Device : binary frames — MP3 audio chunks (streamed as they arrive)
      Server  → Device : text  "DONE"  — response stream finished
      Server  → Device : text  "ERROR:<msg>" — processing error

    Sending new audio while a response is still streaming cancels the
    in-flight stream immediately and starts processing the new utterance.
    """
    # 1. Authenticate via query-param token (WebSocket upgrade cannot send
    #    an Authorization header from most embedded/IoT clients).
    #    When ENABLE_AUTH=false (local dev), skip validation and use the
    #    same stub user that HTTP endpoints receive via get_current_user.
    if not ENABLE_AUTH:
        user = _DEV_STUB_USER
        user_id: str = user["_id"]
    else:
        payload = decode_access_token(token)
        if payload is None:
            await websocket.close(code=4001, reason="Invalid token")
            return

        user_id = payload.get("sub", "")
        if not user_id:
            await websocket.close(code=4001, reason="Invalid token")
            return

        user = await asyncio.to_thread(mongo_db["users"].find_one, {"_id": user_id})
        if not user:
            await websocket.close(code=4001, reason="User not found")
            return

    await websocket.accept()
    logger.info(f"[WS] Device connected: {user_id}")

    # Build a thread-safe signal callback.
    # The ReAct agent tools (signal_device_state, search_web, rag_tool) call
    # this from within the sync thread started by asyncio.to_thread().
    # asyncio.run_coroutine_threadsafe posts the send coroutine onto the event
    # loop and blocks the worker thread briefly until the send completes.
    _loop = asyncio.get_event_loop()

    def _make_signal_fn(ws: WebSocket, loop: asyncio.AbstractEventLoop) -> Callable[[str], None]:
        def signal_fn(json_msg: str) -> None:
            fut = asyncio.run_coroutine_threadsafe(ws.send_text(json_msg), loop)
            try:
                fut.result(timeout=5.0)
            except Exception as sig_exc:
                logger.warning("[WS] signal_fn send failed: %s", sig_exc)
        return signal_fn

    signal_fn = _make_signal_fn(websocket, _loop)

    cancel_event: asyncio.Event | None = None

    try:
        while True:
            # 2. Wait for the next audio frame from the device.
            wav_data = await websocket.receive_bytes()

            # Interrupt any in-flight TTS stream before starting a new pipeline.
            if cancel_event is not None:
                cancel_event.set()
            cancel_event = asyncio.Event()
            _active_cancel_events[user_id] = cancel_event

            # 4. (Test mode) Skip STT/LLM entirely — stream pre-baked MP3 test audio.
            # if not ENABLE_AUTH:
            #     logger.info("[WS] Test mode: skipping STT/LLM, streaming test audio")
            #     async for chunk in test_audio_stream():
            #         if cancel_event.is_set():
            #             break
            #         await websocket.send_bytes(chunk)
            #     if not cancel_event.is_set():
            #         await websocket.send_text("DONE")
            #     continue

            # 3. Speech-to-text + language detection.
            result = await asyncio.to_thread(
                lambda: state.sarvam_client.speech_to_text.translate(
                    file=wav_data,
                    model="saaras:v2.5",
                )
            )

            language_code = result.language_code if result.language_code else ""

            logger.info(
                "[WS] STT → language: '%s' | transcript: '%s'",
                language_code,
                (result.transcript or "")[:120],
            )

            if not language_code or language_code not in SUPPORTED_LANGUAGE_CODES:
                logger.warning(f"[WS] Unsupported language: '{language_code}'")
                async for chunk in streaming_audio_response(
                    UNSUPPORTED_LANGUAGE_MESSAGE, language_code="en-IN", output_audio_bitrate="32k"
                ):
                    if cancel_event.is_set():
                        break
                    await websocket.send_bytes(chunk)
                if not cancel_event.is_set():
                    await websocket.send_text("DONE")
                continue

            # 4. Send immediate "thinking" signal so the device shows the
            #    neural-pulse animation with zero latency while STT just
            #    finished. The ReAct agent will then emit "searching" or
            #    "asking" signals autonomously via signal_device_state tool.
            await websocket.send_text('{"type":"agent_state","value":"thinking"}')

            # 5. LLM ReAct agent response.
            #    signal_fn is passed in so agent tools can push WS frames from
            #    inside the sync thread (e.g. "searching" before a Milvus call).
            session_id, is_new_session = get_or_create_device_session_id(user_id=user["_id"])
            response = await asyncio.to_thread(
                chat,
                user_id=str(user["_id"]),
                session_id=session_id,
                query=result.transcript,
                is_new_session=is_new_session,
                grade=user.get("grade"),
                board=user.get("board"),
                personalized=user.get("personalized", False),
                signal_fn=signal_fn,
            )

            # logger.info(
            #     "[WS] STT transcript: '%s' | Agent response (%d chars): '%s'",
            #     (result.transcript or "")[:80],
            #     len(response),
            #     response[:120],
            # )

            # 6. Translate back if the user spoke a non-English language.
            if language_code != "en-IN":
                response = await asyncio.to_thread(
                    translate_text, response, "en-IN", language_code
                )

            # 7. Stream TTS audio back as binary frames.
            async for chunk in streaming_audio_response(response, language_code=language_code, output_audio_bitrate="32k"):
                if cancel_event.is_set():
                    logger.info("[WS] Stream cancelled — new utterance received.")
                    break
                await websocket.send_bytes(chunk)

            if not cancel_event.is_set():
                await websocket.send_text("DONE")

    except WebSocketDisconnect:
        logger.info(f"[WS] Device disconnected: {user_id}")
    except Exception as e:
        logger.error(f"[WS] Unexpected error for {user_id}: {e}")
        try:
            await websocket.send_text(f"ERROR:{e}")
        except Exception:
            pass
    finally:
        if cancel_event is not None:
            cancel_event.set()
        _active_cancel_events.pop(user_id, None)