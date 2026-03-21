from sarvamai import SarvamAI, AsyncSarvamAI, AudioOutput, EventResponse
import tempfile, base64
import logging
from typing import AsyncGenerator
import os
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

client = SarvamAI(api_subscription_key=SARVAM_API_KEY)


async def streaming_audio_response(
    text: str, language_code: str = "en-IN"
) -> AsyncGenerator[bytes, None]:
    """Stream MP3 audio from Sarvam TTS, yielding each chunk as-is from the API."""
    tts_client = AsyncSarvamAI(api_subscription_key=SARVAM_API_KEY)

    try:
        async with tts_client.text_to_speech_streaming.connect(
            model="bulbul:v2", send_completion_event=True
        ) as ws:
            await ws.configure(target_language_code=language_code, speaker="anushka")
            await ws.convert(text)
            await ws.flush()

            async for message in ws:
                if isinstance(message, AudioOutput):
                    yield base64.b64decode(message.data.audio)
                elif isinstance(message, EventResponse):
                    if message.data.event_type == "final":
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


async def generate_full_audio(text: str, language_code: str = "en-IN") -> bytes:
    """Generate complete TTS audio for the given text. Returns all audio bytes at once."""
    tts_client = AsyncSarvamAI(api_subscription_key=SARVAM_API_KEY)
    audio_bytes = bytearray()
    try:
        async with tts_client.text_to_speech_streaming.connect(model="bulbul:v2", send_completion_event=True) as ws:
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
        logger.error(f"Error generating audio: {e}")
        raise
    return bytes(audio_bytes)