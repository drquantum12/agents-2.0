from sarvamai import SarvamAI, AsyncSarvamAI, AudioOutput, EventResponse
import tempfile, base64
import logging
from typing import AsyncGenerator
import os
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# ---------------------------------------------------------------------------
# Audio streaming tuning constants
# ---------------------------------------------------------------------------
# Accumulate this much audio before yielding the FIRST chunk.  This gives the
# client device a comfortable playback head-start (~5-8 s at 128 kbps) so it
# can absorb later network / generation jitter — the same reason file-based
# streaming sounds smooth.
INITIAL_BUFFER_BYTES = 100 * 1024   # 100 KB

# After the initial burst, yield in smaller pieces to keep memory low while
# still delivering complete MP3 frames.
STREAM_CHUNK_BYTES = 24 * 1024      # 24 KB
# ---------------------------------------------------------------------------

client = SarvamAI(api_subscription_key=SARVAM_API_KEY)


# ---------------------------------------------------------------------------
# MP3 frame helpers – ensure we never split a chunk mid-frame
# ---------------------------------------------------------------------------
# Bitrates in kbps indexed by (mpeg_version_bits, layer_bits, bitrate_index).
# Only the combinations used by common TTS output are listed.
_BITRATES = {
    # MPEG-1
    (3, 1): [0,32,40,48,56,64,80,96,112,128,160,192,224,256,320,0],   # Layer III
    (3, 2): [0,32,48,56,64,80,96,112,128,160,192,224,256,320,384,0],   # Layer II
    (3, 3): [0,32,64,96,128,160,192,224,256,288,320,352,384,416,448,0], # Layer I
    # MPEG-2 / 2.5  (Layer III & II share the same row)
    (2, 1): [0,8,16,24,32,40,48,56,64,80,96,112,128,144,160,0],
    (2, 2): [0,8,16,24,32,40,48,56,64,80,96,112,128,144,160,0],
    (2, 3): [0,32,48,56,64,80,96,112,128,144,160,176,192,224,256,0],
    (0, 1): [0,8,16,24,32,40,48,56,64,80,96,112,128,144,160,0],
    (0, 2): [0,8,16,24,32,40,48,56,64,80,96,112,128,144,160,0],
    (0, 3): [0,32,48,56,64,80,96,112,128,144,160,176,192,224,256,0],
}

_SAMPLE_RATES = {
    3: [44100, 48000, 32000],   # MPEG-1
    2: [22050, 24000, 16000],   # MPEG-2
    0: [11025, 12000,  8000],   # MPEG-2.5
}


def _mp3_frame_length(data: bytes, offset: int) -> int | None:
    """Return the byte-length of the MP3 frame starting at *offset*, or None."""
    if offset + 4 > len(data):
        return None
    b0, b1, b2 = data[offset], data[offset + 1], data[offset + 2]
    if b0 != 0xFF or (b1 & 0xE0) != 0xE0:
        return None

    ver   = (b1 >> 3) & 0x03          # 0=2.5, 2=V2, 3=V1
    layer = (b1 >> 1) & 0x03          # 1=III, 2=II, 3=I
    br_i  = (b2 >> 4) & 0x0F
    sr_i  = (b2 >> 2) & 0x03
    pad   = (b2 >> 1) & 0x01

    if ver == 1 or layer == 0 or br_i == 0 or br_i == 15 or sr_i == 3:
        return None
    row = _BITRATES.get((ver, layer))
    sr_row = _SAMPLE_RATES.get(ver)
    if row is None or sr_row is None:
        return None

    bitrate = row[br_i] * 1000
    sr = sr_row[sr_i]
    if layer == 3:                           # Layer I
        return (12 * bitrate // sr + pad) * 4
    spf = 1152 if ver == 3 else 576          # samples per frame
    return spf * bitrate // (8 * sr) + pad


def _frame_aligned_split(buf: bytearray, target: int) -> int:
    """Return the largest offset <= *target* that falls on an MP3 frame boundary.

    Walks complete frames from the start of *buf*.  If no valid frame is found
    the function falls back to *target* (best-effort).
    """
    pos = 0
    last_boundary = 0
    while pos < len(buf) - 3 and pos < target:
        flen = _mp3_frame_length(buf, pos)
        if flen and flen > 0 and pos + flen <= len(buf):
            pos += flen
            last_boundary = pos
            if pos >= target:
                return pos          # exact or just past target — still frame-aligned
        else:
            pos += 1                # skip non-sync byte
    return last_boundary or target  # fallback keeps streaming moving


# ---------------------------------------------------------------------------
# Core TTS streaming generator
# ---------------------------------------------------------------------------
async def streaming_audio_response(
    text: str, language_code: str = "en-IN"
) -> AsyncGenerator[bytes, None]:
    """Stream MP3 audio from Sarvam TTS with smooth playback.

    Strategy
    --------
    1. **Initial pre-buffer** – accumulate >= INITIAL_BUFFER_BYTES before
       yielding the first chunk.  This gives the receiving device enough audio
       runway (~5-8 s) to absorb later jitter — exactly why file-based
       streaming already sounds smooth.
    2. **Frame-aligned splitting** – every chunk boundary is placed on an MP3
       frame edge so the decoder never sees a partial frame (which causes
       clicks / pops).
    3. **Remainder flush** – anything left after the TTS stream ends is
       yielded immediately.
    """
    tts_client = AsyncSarvamAI(api_subscription_key=SARVAM_API_KEY)

    audio_buffer = bytearray()
    initial_yielded = False

    try:
        async with tts_client.text_to_speech_streaming.connect(
            model="bulbul:v2", send_completion_event=True
        ) as ws:
            await ws.configure(target_language_code=language_code, speaker="anushka")
            await ws.convert(text)
            await ws.flush()

            async for message in ws:
                if isinstance(message, AudioOutput):
                    audio_buffer.extend(base64.b64decode(message.data.audio))

                    if not initial_yielded:
                        # ---- Phase 1: fill the pre-buffer ----
                        if len(audio_buffer) >= INITIAL_BUFFER_BYTES:
                            split = _frame_aligned_split(audio_buffer, INITIAL_BUFFER_BYTES)
                            yield bytes(audio_buffer[:split])
                            del audio_buffer[:split]
                            initial_yielded = True
                    else:
                        # ---- Phase 2: stream in smaller frame-aligned chunks ----
                        while len(audio_buffer) >= STREAM_CHUNK_BYTES:
                            split = _frame_aligned_split(audio_buffer, STREAM_CHUNK_BYTES)
                            yield bytes(audio_buffer[:split])
                            del audio_buffer[:split]

                elif isinstance(message, EventResponse):
                    if message.data.event_type == "final":
                        break

            # Flush whatever remains (could be the entire audio for short texts)
            if audio_buffer:
                yield bytes(audio_buffer)

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