from sarvamai import SarvamAI, AsyncSarvamAI, AudioOutput, EventResponse
import tempfile, base64
import logging
from typing import AsyncGenerator
import os
import asyncio, random
from app.state import state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHUNK_SIZE_BYTES = 8 * 1024   # 8 KB — at 64kbps the device drains ~8KB/sec; sending 32KB
                               # chunks created 4-second gaps where the stream buffer ran
                               # dry, risking ERR_MP3_INDATA_UNDERFLOW and bit-reservoir drift.

# 12 silent MPEG-2 Layer 3 frames prepended to every TTS stream.
#
# Why: Sarvam bulbul:v2 uses the MP3 bit-reservoir — frame N borrows bits
# from frame N-1.  At cold start Helix has no prior frame data, so it reads
# uninitialized memory and produces corrupted PCM for the first 1-2 frames
# (heard as "sport" → "dports", "Arjun" → "ojun").  Helix's 512-tap
# synthesis filter-bank also starts cold, adding a second distortion source.
#
# Fix: yield these frames BEFORE the TTS bytes.  They are fully valid,
# parseable MPEG-2 frames that Helix syncs on and decodes as silence.
# After 12 frames (~313 ms) both the bit-reservoir state and the synthesis
# filter-bank history are in steady state, so the first real speech phoneme
# arrives into a warm decoder and plays back correctly.
#
# Frame spec  MPEG-2 · Layer 3 · 64 kbps · 22 050 Hz · Mono · No CRC:
#   Header    : FF F3 80 C4
#   Side-info : 9 bytes 0x00  (main_data_begin=0, part2_3_length=0)
#   Main data : 195 bytes 0x00 (no Huffman payload → zero PCM)
#   Frame size: 208 bytes  (= floor(72 × 64000 / 22050))
#   Frame dur : 26.1 ms    (576 samples @ 22 050 Hz)
#   12 frames : ≈ 313 ms warm-up silence
_HELIX_WARMUP_MP3: bytes = (bytes([0xFF, 0xF3, 0x80, 0xC4]) + bytes(204)) * 12

async def test_audio_stream():
    # Helper for testing the stream from file
    try:
        with open("app/data/sample.mp3", "rb") as audio_file:
            while chunk := audio_file.read(CHUNK_SIZE_BYTES):
                yield chunk
                await asyncio.sleep(0)
    except FileNotFoundError:
        yield b'Audio file not found. Run /raw-voice-assistant or /voice-assistant first.'
        await asyncio.sleep(0)
        

# testing audio stream with random network jitters
async def test_audio_stream_with_jitter():
    # Helper for testing the stream from file
    try:
        with open("app/data/audio_out_32k.mp3", "rb") as audio_file:
            while chunk := audio_file.read(CHUNK_SIZE_BYTES):
                yield chunk
                await asyncio.sleep(0)
    except FileNotFoundError:
        yield b'Audio file not found. Run /raw-voice-assistant or /voice-assistant first.'
        await asyncio.sleep(0)

async def streaming_audio_response(
    text: str, language_code: str = "en-IN",
    save_response: bool = False,
    output_audio_bitrate: str = "64k",
    pace: float = 0.85,
    speech_sample_rate: int = 22050,
    speaker: str = "anushka",
    pitch: float = 0.0,
    loudness: float = 1.0,
    enable_preprocessing: bool = False,

) -> AsyncGenerator[bytes, None]:
    """Stream MP3 audio from Sarvam TTS, yielding each chunk as-is from the API."""

    # Warm up Helix's bit-reservoir and synthesis filter-bank before the
    # first real TTS phoneme.  See _HELIX_WARMUP_MP3 for full explanation.
    yield _HELIX_WARMUP_MP3
    await asyncio.sleep(0)

    audio_buffer = bytearray()
    try:
        async with state.async_sarvam_client.text_to_speech_streaming.connect(
            model="bulbul:v2", send_completion_event=True
        ) as ws:
            await ws.configure(
                target_language_code=language_code,
                speaker=speaker,
                pitch=pitch,
                loudness=loudness,
                speech_sample_rate=speech_sample_rate,
                enable_preprocessing=enable_preprocessing,
                output_audio_bitrate=output_audio_bitrate,
                pace=pace,
            )
            await ws.convert(text)
            await ws.flush()
            if save_response:
                with open(f"app/data/audio_out_{speech_sample_rate}_{output_audio_bitrate}_{pace}.mp3", "wb") as f:
                    async for message in ws:
                        if isinstance(message, AudioOutput):
                            audio_chunk = base64.b64decode(message.data.audio)
                            audio_buffer.extend(audio_chunk)
                            f.write(audio_chunk)
                            if len(audio_buffer) >= CHUNK_SIZE_BYTES:
                                yield bytes(audio_buffer)
                                audio_buffer.clear()
                                await asyncio.sleep(0)  # yield control so other coroutines can run
                        elif isinstance(message, EventResponse):
                            if message.data.event_type == "final":
                                if audio_buffer:
                                    yield bytes(audio_buffer)
                                    await asyncio.sleep(0)
                                break
            else:
                async for message in ws:
                    if isinstance(message, AudioOutput):
                            audio_chunk = base64.b64decode(message.data.audio)
                            audio_buffer.extend(audio_chunk)
                            if len(audio_buffer) >= CHUNK_SIZE_BYTES:
                                yield bytes(audio_buffer)
                                audio_buffer.clear()
                                await asyncio.sleep(0)  # yield control so other coroutines can run
                    elif isinstance(message, EventResponse):
                        if message.data.event_type == "final":
                            if audio_buffer:
                                yield bytes(audio_buffer)
                                await asyncio.sleep(0)
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