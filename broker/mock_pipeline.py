import asyncio

async def mock_streaming_pipeline(audio_chunk: bytes) -> bytes:
    """Simulates the sequential penalty of STT -> LLM -> TTS pipeline.
        Uses asyncio.sleep() to mimic network latency."""
    
    #Simulate processing delay(trying 300 ms)
    await asyncio.sleep(0.3)

    #Return dummy byte streams for testing without LLM APIs for now
    dummy_audio_bytes = b'\x00\xFF' * 1024
    return dummy_audio_bytes