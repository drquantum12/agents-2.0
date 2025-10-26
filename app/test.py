from sarvamai import SarvamAI, AsyncSarvamAI, AudioOutput
import base64, asyncio

SARVAM_API_KEY="sk_7ntwh8wx_G1lfv0mF3wtkdsAV3B9G3Ezl"
client = SarvamAI(api_subscription_key=SARVAM_API_KEY)

async def streaming_audio_response(text: str, language_code: str = "en-IN"):
    """Stream TTS audio from SarvamAI, save a copy as MP3, and yield chunks for HTTP streaming.

    SarvamAI returns base64-encoded MP3 bytes. Writing those bytes into a file named
    with a .wav extension (or assuming WAV headers) will produce a corrupt/unplayable file.
    We save the raw bytes to `output.mp3` and flush frequently so the file can be opened
    while streaming and after the response completes.
    """
    buffer = bytearray()

    # Open a file to save the audio (MP3)
    with open("output.mp3", "wb") as audio_file:
        async with client.text_to_speech_streaming.connect(model="bulbul:v2", send_completion_event=True) as ws:
            await ws.configure(target_language_code=language_code, speaker="anushka")
            await ws.convert(text)
            await ws.flush()

            async for message in ws:
                if isinstance(message, AudioOutput):
                    buffer.extend(base64.b64decode(message.data.audio))

                    # yield when buffer is larger than 50KB
                    if len(buffer) > 50 * 1024:  # 50KB
                        chunk = bytes(buffer)
                        # write then flush to make the file usable during/after streaming
                        audio_file.write(chunk)
                        audio_file.flush()
                        yield chunk
                        buffer.clear()

            # write any remaining data
            if buffer:
                final_chunk = bytes(buffer)
                audio_file.write(final_chunk)
                audio_file.flush()
                yield final_chunk
                buffer.clear()

if __name__ == "__main__":
    sample_query = "Explain the theory of relativity in simple terms and give real life examples."
    async def _run():
        # Consume the async generator so the TTS stream actually runs and writes the file.
        total = 0
        async for chunk in streaming_audio_response(sample_query, language_code="en-IN"):
            total += len(chunk)
            print(f"Received chunk: {len(chunk)} bytes (total={total})")
        print(f"Streaming complete, total bytes written: {total}")

    asyncio.run(_run())