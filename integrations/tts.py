import os
import asyncio
import httpx
import re


class DeepgramTTS:
    def __init__(self):
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPGRAM_API_KEY environment variable is missing.")
            
        #Removing linear16 so Deepgram defaults to a standard, highly compressed MP3
        self.url = "https://api.deepgram.com/v1/speak?model=aura-asteria-en"

    async def generate_audio(self, tts_queue: asyncio.Queue, audio_out_queue: asyncio.Queue):
        print("☁️ Deepgram Aura TTS Engine connected and ready.")

        async def fetch_tts(client, clean_chunk):
            headers = {
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {"text": clean_chunk}
            try:
                #Hard timeout of 5 seconds to prevent 25-second deadlocks
                response = await client.post(self.url, headers=headers, json=payload, timeout=5.0)
                response.raise_for_status()
                
                audio_data = response.content
                await audio_out_queue.put(audio_data)
            except Exception as e:
                print(f"⚠️ [Deepgram TTS Error]: {e}")
        
        async with httpx.AsyncClient() as client:
            while True:
                text_chunk = await tts_queue.get()
                
                if not text_chunk:
                    continue

                clean_chunk = re.sub(r'[*_#]', '', text_chunk)
                if "N.O.V.A." in clean_chunk:
                    clean_chunk = clean_chunk.replace("N.O.V.A.", "NOVA")
                payload = {"text": clean_chunk}

                print(f"🎙️ [Cloud TTS] Synthesizing: '{clean_chunk}'")
                
                asyncio.create_task(fetch_tts(client, clean_chunk))
