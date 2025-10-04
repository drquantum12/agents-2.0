import os
import asyncio
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from fastapi.middleware import cors as middleware
import tempfile
from sarvamai import SarvamAI, AsyncSarvamAI, AudioOutput
import base64
# from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from prompts import AI_TUTOR_PROMPT
from db_utility.vector_db import VectorDB

# llm = ChatOllama(base_url="http://localhost:11434",
#                   model="llama3.2:latest",
#                   temperature=0)

llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-lite",
            temperature=1,
            max_output_tokens=8192,
            timeout=30,
            max_retries=2,)

vector_db = VectorDB()

app = FastAPI()

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

if not SARVAM_API_KEY:
    raise EnvironmentError("SARVAM_API_KEY environment variable not set")

app.add_middleware(
    middleware.CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# model = whisper.load_model("base", device="cpu")
client = SarvamAI(api_subscription_key=SARVAM_API_KEY)

# Async generator for streaming audio
async def streaming_audio_response(text: str, language_code: str = "en-IN"):
    client = AsyncSarvamAI(api_subscription_key=SARVAM_API_KEY)
    
    # Open a file to save the audio
    with open("output.wav", "wb") as audio_file:
        async with client.text_to_speech_streaming.connect(model="bulbul:v2") as ws:
            await ws.configure(target_language_code=language_code, speaker="anushka")
            await ws.convert(text)
            await ws.flush()

            async for message in ws:
                if isinstance(message, AudioOutput):
                    audio_chunk = base64.b64decode(message.data.audio)
                    # Write to file and yield for streaming
                    audio_file.write(audio_chunk)
                    yield audio_chunk  # <-- stream bytes immediately

            # Close socket when finished
            if hasattr(ws, "_websocket") and not ws._websocket.closed:
                await ws._websocket.close()

async def test_audio_stream():
    with open("output.wav", "rb") as audio_file:
        while chunk := audio_file.read(100000):  # 100KB chunks
            yield chunk
            await asyncio.sleep(0)

def chunk_text(text, max_length=2000):
    """Splits text into chunks of at most max_length characters while preserving word boundaries."""
    chunks = []

    while len(text) > max_length:
        split_index = text.rfind(" ", 0, max_length)  # Find the last space within limit
        if split_index == -1:
            split_index = max_length  # No space found, force split at max_length

        chunks.append(text[:split_index].strip())  # Trim spaces before adding
        text = text[split_index:].lstrip()  # Remove leading spaces for the next chunk

    if text:
        chunks.append(text.strip())  # Add the last chunk

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

        translated_text = response.translated_text
        print(f"\n=== Translated Chunk {idx + 1} ===\n{translated_text}\n")
        translated_texts.append(translated_text)
    return " ".join(translated_texts)


@app.post("/voice-assistant")
async def voice_assistant(file: UploadFile = File(...)):
    try:
        # return StreamingResponse(
        #     test_audio_stream(),
        #     media_type="audio/wav"
        # )
    
    
        audio_data = await file.read()
        with tempfile.NamedTemporaryFile(delete=True, suffix=".wav") as temp_audio:
            temp_audio.write(audio_data)
            temp_audio.flush()
            result = client.speech_to_text.translate(
            file=temp_audio,
            model="saaras:v2.5"
        )
        
        # recording sample response:
        # with open("sample_response.txt", "w") as f:
        #     f.write(str(result))

        print(f"Translation: {result.transcript}")

        context, _ = vector_db.get_similar_documents(result.transcript, top_k=3)
        print(f"Context retrieved: {context}")

        prompt = AI_TUTOR_PROMPT.invoke({"query": result.transcript, "context": context})
        response = llm.invoke(prompt).content.strip()

        print(f"LLM response obtained: {response}")

        response = translate_text(response, source_language_code="en-IN", target_language_code=result.language_code)

        return StreamingResponse(
            streaming_audio_response(response, language_code=result.language_code),
            media_type="audio/wav"
        )
    except Exception as e:
        print(e)
        return {"error": str(e)}
    
@app.get("/testing-audio-stream")
async def test_tts_stream():
    sample_text = "Hello, this is a test of the text to speech streaming endpoint. Have a great day!"
    return StreamingResponse(
        streaming_audio_response(sample_text),
        media_type="audio/wav"
    )


# if __name__ == "__main__":
#     result = model.transcribe(audio_file_path)
#     print(result["text"])


# @app.get("/testing-audio-stream")
# async def test_audio_stream():
#     audio_file_path = os.path.join(os.path.dirname(__file__), "data", "harvard.wav")
#     chunk_size = 100000  # 100KB chunks
    
#     def iterfile():
#         with open(audio_file_path, "rb") as audio_file:
#             while chunk := audio_file.read(chunk_size):
#                 yield chunk
#     return StreamingResponse(iterfile(), media_type="audio/wav")