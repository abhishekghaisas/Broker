import os
import asyncio
import httpx

class DeepgramTTS:
    def __init__(self):
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPGRAM_API_KEY environment variable is missing.")
            
        # Removing linear16 so Deepgram defaults to a standard, highly compressed MP3
        self.url = "https://api.deepgram.com/v1/speak?model=aura-asteria-en"

    async def generate_audio(self, tts_queue: asyncio.Queue, audio_out_queue: asyncio.Queue):
        print("☁️ Deepgram Aura TTS Engine connected and ready.")
        
        async with httpx.AsyncClient() as client:
            while True:
                text_chunk = await tts_queue.get()
                
                if not text_chunk:
                    continue

                print(f"🎙️ [Cloud TTS] Synthesizing: '{text_chunk}'")
                
                headers = {
                    "Authorization": f"Token {self.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {"text": text_chunk}

                try:
                    # Request the audio and read the entire MP3 buffer (takes ~100-200ms)
                    response = await client.post(self.url, headers=headers, json=payload, timeout=10.0)
                    response.raise_for_status()
                    
                    audio_data = response.content
                    # Send the complete MP3 down the WebSocket to the browser
                    await audio_out_queue.put(audio_data)
                            
                except Exception as e:
                    print(f"⚠️ [Deepgram TTS Error]: {e}")