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
import os
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["Agent"])
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")


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

    # Pick a contextual filler phrase based on query type (zero LLM cost)
    filler_phrase = pick_filler_phrase(result.transcript)
    logger.info(f"Filler phrase: '{filler_phrase}' for query: {result.transcript[:50]}")

    # Launch filler TTS and agent processing CONCURRENTLY
    # Filler TTS completes in ~200-400ms, agent takes ~2-5s
    # User hears filler audio almost immediately instead of silence
    filler_task = asyncio.create_task(generate_filler_audio(filler_phrase, language_code=language_code))
    agent_task = asyncio.create_task(asyncio.to_thread(run_agent, user=user, query=result.transcript, session_id=session_id))

    # Wait for filler audio first (should be very fast ~200-400ms)
    filler_audio = await filler_task

    async def combined_audio_stream():
        # 1. Yield filler audio immediately so user hears something right away
        if filler_audio:
            yield filler_audio
            await asyncio.sleep(0)

        # 2. Wait for agent response (may already be done by now since filler was fast)
        response = await agent_task

        # 3. Translate if needed
        final_response = response
        if language_code != "en-IN":
            final_response = await asyncio.to_thread(translate_text, response, "en-IN", language_code)

        # 4. Stream the actual response audio with sentence-level pipelining
        async for chunk in sentence_pipelined_tts(final_response, language_code=language_code):
            yield chunk

    headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    
    return StreamingResponse(
        combined_audio_stream(),
        media_type="audio/mpeg",
        headers=headers
    )