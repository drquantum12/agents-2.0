from sarvamai import SarvamAI, AsyncSarvamAI, AudioOutput, EventResponse
import tempfile, base64
import logging
from typing import AsyncGenerator
import os
import asyncio
from app.state import state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHUNK_SIZE_BYTES = 32 * 1024  # 32 KB

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

async def streaming_audio_response(
    text: str, language_code: str = "en-IN"
) -> AsyncGenerator[bytes, None]:
    """Stream MP3 audio from Sarvam TTS, yielding each chunk as-is from the API."""

    audio_buffer = bytearray()
    try:
        async with state.async_sarvam_client.text_to_speech_streaming.connect(
            model="bulbul:v2", send_completion_event=True
        ) as ws:
            await ws.configure(target_language_code=language_code, speaker="anushka")
            await ws.convert(text)
            await ws.flush()

            async for message in ws:
                if isinstance(message, AudioOutput):
                    audio_chunk = base64.b64decode(message.data.audio)
                    audio_buffer.extend(audio_chunk)
                    # yield chunk
                    if len(audio_buffer) >= CHUNK_SIZE_BYTES:
                        yield bytes(audio_buffer)
                        audio_buffer.clear()
                elif isinstance(message, EventResponse):
                    if message.data.event_type == "final":
                        if audio_buffer:
                            yield bytes(audio_buffer)
                        break

    except Exception as e:
        logger.error(f"Error during audio streaming: {e}")
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
        response = state.sarvam_client.text.translate(
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
