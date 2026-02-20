from sarvamai import SarvamAI, AsyncSarvamAI, AudioOutput, EventResponse
import tempfile, base64
import logging
from typing import AsyncGenerator
import os
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
CHUNK_SIZE_BYTES = 50 * 1024

client = SarvamAI(api_subscription_key=SARVAM_API_KEY)

async def streaming_audio_response(
    text: str, language_code: str = "en-IN"
) -> AsyncGenerator[bytes, None]:
    client = AsyncSarvamAI(api_subscription_key=SARVAM_API_KEY)
    
    audio_buffer = bytearray()
    # Open file in async-safe way (sync I/O is fine here because chunks are small)
    try:
        async with client.text_to_speech_streaming.connect(model="bulbul:v2", send_completion_event=True) as ws:
            await ws.configure(target_language_code=language_code, speaker="anushka")
            
            # Send text and flush once
            await ws.convert(text)
            await ws.flush()

            # Stream chunks as they come
            # with open("data/output.mp3", "wb") as output_file:
            #     async for message in ws:
            #         if isinstance(message, AudioOutput):
            #             audio_chunk = base64.b64decode(message.data.audio)
                        
            #             # Write to file immediately
            #             output_file.write(audio_chunk)
            #             output_file.flush()
                        
            #             # Yield to client immediately
            #             yield audio_chunk
            #             await asyncio.sleep(0.5)
                    
            #         elif isinstance(message, EventResponse):
            #             if message.data.event_type == "final":
            #                 break

            async for message in ws:
                if isinstance(message, AudioOutput):
                    audio_chunk = base64.b64decode(message.data.audio)
                    audio_buffer.extend(audio_chunk)
                    
                    # 2. Check if the buffer is big enough to start yielding 50KB chunks
                    while len(audio_buffer) >= CHUNK_SIZE_BYTES:
                        # Extract a 50KB chunk
                        chunk_to_yield = audio_buffer[:CHUNK_SIZE_BYTES]
                        
                        # Remove the yielded chunk from the buffer
                        del audio_buffer[:CHUNK_SIZE_BYTES]
                        
                        # Yield the 50KB chunk to the client
                        yield bytes(chunk_to_yield)
                        await asyncio.sleep(0.5)
                
                elif isinstance(message, EventResponse):
                    if message.data.event_type == "final":
                        break
            
            # Yield any remaining audio in the buffer
            if audio_buffer:
                yield bytes(audio_buffer)

    except Exception as e:
        logger.error(f"Error during audio streaming and saving: {e}")
        raise

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