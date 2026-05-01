import os
import asyncio
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi import status
from fastapi.middleware import cors as middleware
from sarvamai import SarvamAI, AsyncSarvamAI
from langchain_google_genai import ChatGoogleGenerativeAI
# Assuming these are defined elsewhere
from app.agents import init_agent
from app.state import state
from app.utility.hiveMQ import HiveMQClient
# from db_utility.vector_db import VectorDB 
import logging
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1
BIT_DEPTH = 32

# --- Initialization (Assuming classes like VectorDB, AI_TUTOR_PROMPT are defined elsewhere) ---
llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-lite",
            temperature=0.6,
            max_output_tokens=8192,
            timeout=30,
            max_retries=2,)

@asynccontextmanager
async def lifespan(app: FastAPI):
    state.async_sarvam_client = AsyncSarvamAI(api_subscription_key=os.getenv("SARVAM_API_KEY"))
    state.sarvam_client = SarvamAI(api_subscription_key=os.getenv("SARVAM_API_KEY"))
    state.mqtt_client = HiveMQClient()
    init_agent(db_name="neurosattva")
    try:
        await state.mqtt_client.connect()
    except Exception as e:
        logger.error(f"HiveMQ connection failed: {e}")
    yield
    state.async_sarvam_client = None
    state.sarvam_client = None
    await state.mqtt_client.disconnect()

app = FastAPI(lifespan=lifespan)

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")


app.add_middleware(
    middleware.CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import auth, user, conversation, message, agent, device, notification, mqtt

app.include_router(auth.router, prefix="/api/v1")
app.include_router(user.router, prefix="/api/v1")
app.include_router(conversation.router, prefix="/api/v1")
app.include_router(message.router, prefix="/api/v1")
app.include_router(agent.router, prefix="/api/v1")
app.include_router(notification.router, prefix="/api/v1")
app.include_router(device.router, prefix="/api/v1")
app.include_router(mqtt.router, prefix="/api/v1")


client = SarvamAI(api_subscription_key=SARVAM_API_KEY)

# Import the pre-buffer + frame-aligned streaming implementation from agents
from app.agents.utility import streaming_audio_response

# Legacy local copy removed — single source of truth is app.agents.utility


@app.get("/test-audio-generator")
async def test_audio_generator():
    sample_text = """
Robotic intelligence is the integration of Artificial Intelligence (AI) into physical robots, enabling them to perceive, reason, learn, and act autonomously rather than just following pre-programmed instructions. By combining AI "brains" with robotic "bodies," these systems process sensor data to navigate, solve problems, and interact with humans and environments.
"""
    return StreamingResponse(
        streaming_audio_response(sample_text, save_response=True, output_audio_bitrate="32k", pace=0.9),
        media_type="audio/mpeg"
    )

async def test_audio_stream():
    # Helper for testing the stream from file
    try:
        with open("app/data/sample.mp3", "rb") as audio_file:
            while chunk := audio_file.read(100000):  # 100KB chunks
                yield chunk
                await asyncio.sleep(0)
    except FileNotFoundError:
        yield b'Audio file not found. Run /raw-voice-assistant or /voice-assistant first.'
        await asyncio.sleep(0)


def chunk_text(text, max_length=2000):
    """Splits text into chunks of at most max_length characters while preserving word boundaries."""
    chunks = []
    while len(text) > max_length:
        split_index = text.rfind(" ", 0, max_length)
        if split_index == -1:
            split_index = max_length
        chunks.append(text[:split_index].strip())
        text = text[split_index:].lstrip()
    if text:
        chunks.append(text.strip())
    return chunks

def translate_text(text, source_language_code="hi-IN", target_language_code="en-IN"):
    text_chunks = chunk_text(text, max_length=2000)
    translated_texts = []
    for idx, chunk in enumerate(text_chunks):
        response = client.text.translate(
            input=chunk,
            source_language_code=source_language_code,
            target_language_code=target_language_code,
            speaker_gender="Female",
            mode="formal",
            model="sarvam-translate:v1",
            enable_preprocessing=False,
        )
        translated_texts.append(response.translated_text)
    return " ".join(translated_texts)

@app.post("/raw-voice-assistant")
async def handle_audio_upload(request: Request):
    """
    Handles the raw 'audio/wav' binary upload from the ESP32.
    """
    try:
        wav_data = await request.body()
        
        
        # Debugging: saving wav data as audio_input.wav
        # with wave.open("app/data/input_32bit.wav", "wb") as wf:
        #     wf.setnchannels(CHANNELS)
        #     wf.setsampwidth(BIT_DEPTH//8)
        #     wf.setframerate(SAMPLE_RATE)
        #     wf.writeframes(wav_data)

        with open("app/data/input_32bit.wav", "wb") as f:
            f.write(wav_data)

        # print(f"Sending audio stream...\n")

        # with tempfile.NamedTemporaryFile(delete=True, suffix=".wav") as temp_audio:
        #     temp_audio.write(wav_data)
        #     temp_audio.flush()
        #     result = client.speech_to_text.translate(
        #     file=temp_audio,
        #     model="saaras:v2.5"
        # )
        # logger.info(f"Translation: {result.transcript}")
        
        # content_type = request.headers.get("content-type")
        # logger.info(f"Received request from ESP32. Content-Type: {content_type}")

        # # Note: vector_db usage assumes the class is defined/imported correctly
        # # context, _ = vector_db.get_similar_documents(result.transcript, top_k=3)
        # # logger.info(f"Context retrieved: {context}")

        # prompt = AI_DEVICE_TUTOR_PROMPT.invoke({"query": result.transcript})
        # response = llm.invoke(prompt).content.strip()

        # logger.info(f"LLM response obtained: {response}")

        # if result.language_code != "en-IN":
        #     response = translate_text(response, source_language_code="en-IN", target_language_code=result.language_code)

        # headers = {
        #     "Cache-Control": "no-cache",
        #     "Connection": "keep-alive",
        #     "X-Accel-Buffering": "no"
        # }
        
        # return StreamingResponse(
        #     streaming_audio_response(response, language_code=result.language_code),
        #     media_type="audio/mpeg",
        #     headers=headers
        # )

        # return StreamingResponse(
        #     test_audio_stream(),
        #     media_type="audio/mpeg",
        #     headers=headers
        # )

        return JSONResponse(content="Successfully saved!", status_code=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error during audio processing: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"message": "Internal Server Error during processing"}
        )

@app.get("/testing-audio-stream")
async def test_tts_stream(request: Request):
    """
    Tests the streaming functionality by reading the last saved output.mp3 file.
    """
    return StreamingResponse(
        test_audio_stream(),
        media_type="audio/mpeg"
    )    

@app.post("/testing-audio-stream")
async def test_tts_stream(request: Request):
    """
    Tests the streaming functionality by reading the last saved output.mp3 file.
    """
    return StreamingResponse(
        test_audio_stream(),
        media_type="audio/mpeg"
    )

