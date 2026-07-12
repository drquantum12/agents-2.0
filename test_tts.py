import asyncio, os
from sarvamai import AsyncSarvamAI, SarvamAI
from app.state import state
from app.agents.utility import streaming_audio_response

async def test():
    state.async_sarvam_client = AsyncSarvamAI(api_subscription_key=os.getenv("SARVAM_API_KEY"))
    state.sarvam_client = SarvamAI(api_subscription_key=os.getenv("SARVAM_API_KEY"))
    total = 0
    async for chunk in streaming_audio_response("Hello, this is a test.", language_code="en-IN"):
        total += len(chunk)
    print(f"TTS produced {total} bytes")

asyncio.run(test())
