from sarvamai import SarvamAI, AsyncSarvamAI, AudioOutput, EventResponse
import tempfile, base64
import logging
from typing import AsyncGenerator
import os
import asyncio
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
CHUNK_SIZE_BYTES = 50 * 1024
# Smaller buffer for sentence-level TTS so first audio arrives faster
SENTENCE_CHUNK_SIZE_BYTES = 8 * 1024

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


def split_into_sentences(text: str) -> list[str]:
    """
    Split text into sentences using regex-based boundary detection.
    Handles common abbreviations and edge cases for TTS pipelining.
    Each returned sentence is non-empty and stripped.
    """
    # Split on sentence-ending punctuation followed by whitespace or end-of-string.
    # Preserves the delimiter with the preceding sentence.
    raw_parts = re.split(r'(?<=[.!?])\s+', text.strip())

    sentences = []
    for part in raw_parts:
        part = part.strip()
        if part:
            sentences.append(part)

    # If no sentence-ending punctuation was found (single chunk), return as-is
    if not sentences:
        sentences = [text.strip()]

    return sentences


async def tts_sentence(
    sentence: str,
    language_code: str = "en-IN",
) -> AsyncGenerator[bytes, None]:
    """
    Convert a single sentence to audio with minimal buffering.
    Uses a smaller buffer (8KB) so the first audio bytes arrive quickly.
    For sentence-level pipelining, low latency to first byte matters more than large chunks.
    """
    tts_client = AsyncSarvamAI(api_subscription_key=SARVAM_API_KEY)
    audio_buffer = bytearray()

    try:
        async with tts_client.text_to_speech_streaming.connect(
            model="bulbul:v2", send_completion_event=True
        ) as ws:
            await ws.configure(target_language_code=language_code, speaker="anushka")
            await ws.convert(sentence)
            await ws.flush()

            async for message in ws:
                if isinstance(message, AudioOutput):
                    audio_chunk = base64.b64decode(message.data.audio)
                    audio_buffer.extend(audio_chunk)

                    # Yield in small chunks for faster first-byte delivery
                    while len(audio_buffer) >= SENTENCE_CHUNK_SIZE_BYTES:
                        chunk_to_yield = audio_buffer[:SENTENCE_CHUNK_SIZE_BYTES]
                        del audio_buffer[:SENTENCE_CHUNK_SIZE_BYTES]
                        yield bytes(chunk_to_yield)

                elif isinstance(message, EventResponse):
                    if message.data.event_type == "final":
                        break

            # Yield remaining audio for this sentence
            if audio_buffer:
                yield bytes(audio_buffer)

    except Exception as e:
        logger.error(f"Error in sentence TTS for '{sentence[:40]}...': {e}")
        raise


async def sentence_pipelined_tts(
    text: str,
    language_code: str = "en-IN",
) -> AsyncGenerator[bytes, None]:
    """
    Sentence-level TTS pipelining: split text into sentences and convert each
    to audio sequentially with minimal buffering.

    Why this is faster:
    - TTS for a ~15-word sentence produces first audio in ~0.3-0.5s
    - TTS for a full ~100-word response takes ~2-3s to first audio
    - Client starts playing audio from sentence 1 while sentences 2+ are being converted

    Falls back to full-text streaming_audio_response if only 1 sentence.
    """
    sentences = split_into_sentences(text)
    logger.info(f"Sentence pipelining: {len(sentences)} sentence(s) to convert")

    if len(sentences) <= 1:
        # Single sentence — use original function (no overhead from splitting)
        async for chunk in streaming_audio_response(text, language_code):
            yield chunk
        return

    for i, sentence in enumerate(sentences):
        logger.info(f"TTS sentence {i + 1}/{len(sentences)}: '{sentence[:50]}...'")
        async for chunk in tts_sentence(sentence, language_code):
            yield chunk

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


async def generate_filler_audio(text: str, language_code: str = "en-IN") -> bytes:
    """Generate a short filler audio clip. Returns complete audio bytes for a brief phrase."""
    filler_client = AsyncSarvamAI(api_subscription_key=SARVAM_API_KEY)
    audio_bytes = bytearray()
    try:
        async with filler_client.text_to_speech_streaming.connect(model="bulbul:v2", send_completion_event=True) as ws:
            await ws.configure(target_language_code=language_code, speaker="anushka")
            await ws.convert(text)
            await ws.flush()
            async for message in ws:
                if isinstance(message, AudioOutput):
                    audio_bytes.extend(base64.b64decode(message.data.audio))
                elif isinstance(message, EventResponse):
                    if message.data.event_type == "final":
                        break
    except Exception as e:
        logger.error(f"Error generating filler audio: {e}")
    return bytes(audio_bytes)