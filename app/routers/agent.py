import asyncio
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.agents.core_agent import run_agent
from app.utility.security import get_current_user
from app.models.user import User
import tempfile
from app.agents.utility import client, translate_text, streaming_audio_response
from app.agents.agent_memory_controller import get_or_create_device_session_id
import os

router = APIRouter(prefix="/agent", tags=["Agent"])
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")


class QueryRequest(BaseModel):
    query: str
        
@router.post("/query")
async def agent(request: QueryRequest, user: User = Depends(get_current_user)):
    session_id = get_or_create_device_session_id(user_id=user["_id"])
    response = await asyncio.to_thread(run_agent, user=user, query=request.query, session_id=session_id)
    return {"response": response}

async def test_audio_stream():
    # Helper for testing the stream from file
    try:
        with open("app/data/output.mp3", "rb") as audio_file:
            while chunk := audio_file.read(100000):  # 100KB chunks
                yield chunk
                await asyncio.sleep(0)
    except FileNotFoundError:
        yield b'Audio file not found. Run /raw-voice-assistant or /voice-assistant first.'
        await asyncio.sleep(0)
        
@router.post("/device-voice-assistant")
async def device_voice_assistant(request: Request,
                                  user: User = Depends(get_current_user)
                                  ):
    wav_data = await request.body()

    with open("app/data/input_32bit.wav", "wb") as f:
            f.write(wav_data)
    
    # return StreamingResponse(
    #     test_audio_stream(),
    #     media_type="audio/mpeg"
    # )
    
    with tempfile.NamedTemporaryFile(delete=True, suffix=".wav") as temp_audio:
            temp_audio.write(wav_data)
            temp_audio.flush()
            result = client.speech_to_text.translate(
            file=temp_audio,
            model="saaras:v2.5"
        )
    
    session_id = get_or_create_device_session_id(user_id=user["_id"])
    
    response = await asyncio.to_thread(run_agent, user=user, query=result.transcript, session_id=session_id)

    if result.language_code != "en-IN":
        response = translate_text(response, source_language_code="en-IN", target_language_code=result.language_code)
    
    headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
        
    return StreamingResponse(
        streaming_audio_response(response, language_code=result.language_code),
        media_type="audio/mpeg",
        headers=headers
    )