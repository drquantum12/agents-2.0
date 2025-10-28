import os
import asyncio
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi import status
from fastapi.middleware import cors as middleware
import tempfile
from sarvamai import SarvamAI, AsyncSarvamAI, AudioOutput, EventResponse
import base64
from langchain_google_genai import ChatGoogleGenerativeAI
# Assuming these are defined elsewhere
from prompts import AI_TUTOR_PROMPT 
from db_utility.vector_db import VectorDB 
import logging, uvicorn
from typing import AsyncGenerator, Callable

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Initialization (Assuming classes like VectorDB, AI_TUTOR_PROMPT are defined elsewhere) ---
llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-lite",
            temperature=1,
            max_output_tokens=8192,
            timeout=30,
            max_retries=2,)

# Initialize with placeholder instances since actual imports are missing
try:
    vector_db = VectorDB()
except NameError:
    class DummyVectorDB:
        def get_similar_documents(self, query, top_k):
            return "Sample context for the query.", ["doc1"]
    vector_db = DummyVectorDB()
    logger.warning("Using DummyVectorDB as VectorDB class definition was not found.")

try:
    # Assuming AI_TUTOR_PROMPT is a class/object with an invoke method
    from prompts import AI_TUTOR_PROMPT 
except ImportError:
    class DummyPrompt:
        def invoke(self, kwargs):
            return f"The user asked: {kwargs['query']}. Context: {kwargs['context']}"
    # Creating a dummy object to match the usage in the endpoints
    class DummyPromptInvoker:
        def invoke(self, kwargs):
            return DummyPrompt().invoke(kwargs)
    AI_TUTOR_PROMPT = DummyPromptInvoker()
    logger.warning("Using DummyPrompt for AI_TUTOR_PROMPT as definition was not found.")

app = FastAPI()

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")


app.add_middleware(
    middleware.CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = SarvamAI(api_subscription_key=SARVAM_API_KEY)


async def streaming_audio_response(
    text: str, language_code: str = "en-IN"
) -> AsyncGenerator[bytes, None]:
    client = AsyncSarvamAI(api_subscription_key=SARVAM_API_KEY)
    
    # Open file in async-safe way (sync I/O is fine here because chunks are small)
    try:
        async with client.text_to_speech_streaming.connect(model="bulbul:v2", send_completion_event=True) as ws:
            await ws.configure(target_language_code=language_code, speaker="anushka")
            
            # Send text and flush once
            await ws.convert(text)
            await ws.flush()

            # Stream chunks as they come
            with open("output.mp3", "wb") as output_file:
                async for message in ws:
                    if isinstance(message, AudioOutput):
                        audio_chunk = base64.b64decode(message.data.audio)
                        
                        # Write to file immediately
                        output_file.write(audio_chunk)
                        output_file.flush()
                        
                        # Yield to client immediately
                        yield audio_chunk
                        await asyncio.sleep(0.5)
                    
                    elif isinstance(message, EventResponse):
                        if message.data.event_type == "final":
                            break

    except Exception as e:
        logger.error(f"Error during audio streaming and saving: {e}")
        raise

# async def streaming_audio_response(text: str, language_code: str = "en-IN") -> AsyncGenerator[bytes, None]:
#     with open("output_v2.mp3", "wb") as output_file:
#         try:
#             # Initialize Async Client inside the async function
#             client = AsyncSarvamAI(api_subscription_key=SARVAM_API_KEY)
            
#             async with client.text_to_speech_streaming.connect(model="bulbul:v2") as ws:
#                 await ws.configure(target_language_code=language_code, speaker="anushka")
#                 await ws.convert(text)
#                 await ws.flush()

#                 async for message in ws:
#                     if isinstance(message, AudioOutput):
#                         # Decode the base64 chunk
#                         audio_chunk = base64.b64decode(message.data.audio)
                        
#                         # Write chunk to file
#                         output_file.write(audio_chunk)
#                         output_file.flush()
                        
#                         # Yield chunk for streaming
#                         yield audio_chunk

#         except Exception as e:
#             logger.error(f"Error during audio streaming and saving: {e}")
#             # Re-raise the exception for FastAPI to handle
#             raise

@app.get("/test-audio-generator")
async def test_audio_generator():
    sample_text = """
Okay, here's a breakdown of photosynthesis in about 100 words, using the information you provided:

Photosynthesis is how plants make their own food! It's like a plant's personal cooking process. Plants use a green substance called chlorophyll to absorb sunlight. They then take in carbon dioxide from the air and water from the ground. Inside the plant, these ingredients are combined to create sugars, which the plant uses as food for energy and growth. A bonus byproduct of this amazing process is oxygen, which is released into the air. So, plants not only feed themselves, but they also give us the air we breathe!
"""
    return StreamingResponse(
        streaming_audio_response(sample_text),
        media_type="audio/mpeg"
    )

async def test_audio_stream():
    # Helper for testing the stream from file
    try:
        with open("output_v2.mp3", "rb") as audio_file:
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
        with open("audio_input_v2.wav", "wb") as f:
            f.write(wav_data)

        print(f"Sending audio stream...\n")

        with tempfile.NamedTemporaryFile(delete=True, suffix=".wav") as temp_audio:
            temp_audio.write(wav_data)
            temp_audio.flush()
            result = client.speech_to_text.translate(
            file=temp_audio,
            model="saaras:v2.5"
        )
        logger.info(f"Translation: {result.transcript}")
        
        content_type = request.headers.get("content-type")
        logger.info(f"Received request from ESP32. Content-Type: {content_type}")

        # Note: vector_db usage assumes the class is defined/imported correctly
        context, _ = vector_db.get_similar_documents(result.transcript, top_k=3)
        logger.info(f"Context retrieved: {context}")

        prompt = AI_TUTOR_PROMPT.invoke({"query": result.transcript, "context": context})
        response = llm.invoke(prompt).content.strip()

        logger.info(f"LLM response obtained: {response}")

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

        # return StreamingResponse(
        #     test_audio_stream(),
        #     media_type="audio/mpeg",
        #     headers=headers
        # )

    except Exception as e:
        logger.error(f"Error during audio processing: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"message": "Internal Server Error during processing"}
        )

@app.post("/voice-assistant")
async def voice_assistant(file: UploadFile = File(...)):
    try:
        audio_data = await file.read()
        with tempfile.NamedTemporaryFile(delete=True, suffix=".wav") as temp_audio:
            temp_audio.write(audio_data)
            temp_audio.flush()
            result = client.speech_to_text.translate(
            file=temp_audio,
            model="saaras:v2.5"
        )
        
        logger.info(f"Translation: {result.transcript}")

        context, _ = vector_db.get_similar_documents(result.transcript, top_k=3)
        logger.info(f"Context retrieved: {context}")

        prompt = AI_TUTOR_PROMPT.invoke({"query": result.transcript, "context": context})
        response = llm.invoke(prompt).content.strip()

        logger.info(f"LLM response obtained: {response}")

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
    except Exception as e:
        logger.error(f"Error in /voice-assistant endpoint: {e}")
        return {"error": str(e)}
    
@app.get("/testing-audio-stream")
async def test_tts_stream():
    """
    Tests the streaming functionality by reading the last saved output.mp3 file.
    """
    return StreamingResponse(
        test_audio_stream(),
        media_type="audio/mpeg"
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
