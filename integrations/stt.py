import asyncio
import websockets
import json
import os
import time

class StreamingSTT:
    def __init__(self):
        #We will use Deepgram as our STT engine example for optimal latency
        self.api_key = os.getenv("DEEPGRAM_API_KEY", "your_api_key_here")
        self.url = "wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=16000&channels=1&endpointing=500&interim_results=true"
        self.connection = None

    async def connect(self):
        """Establishes the persistent WebSocket connection to the STT provider."""
        self.connection = await websockets.connect(
            self.url,
            additional_headers={"Authorization": f"Token {self.api_key}"},
            open_timeout=20
        )
        print("🟢 STT Engine connected and ready.")

    async def process_audio(self, audio_queue: asyncio.Queue):
        """Pulls raw 20ms audio chunks from the broker queue and streams them to the STT."""
        try:
            while True:
                try:

                    chunk = await asyncio.wait_for(audio_queue.get(), timeout=5.0)

                    if self.connection:
                        await self.connection.send(chunk)
                except asyncio.TimeoutError:
                    if self.connection:
                        keep_alive_msg = json.dumps({"type": "KeepAlive"})
                        await self.connection.send(keep_alive_msg)
        except Exception as e:
            print(f"STT Send Error: {e}")

    async def receive_transcripts(self, token_queue: asyncio.Queue):
        """Listens for returning text tokens and pushes both partial and final transcripts to the router queue."""
        try:
            while True:
                if self.connection:
                    response = await self.connection.recv()
                    data = json.loads(response)
                    
                    #Parse the transcript and finality flag from the JSON payload
                    is_final = data.get("is_final", False)
                    transcript = data.get("channel", {}).get("alternatives", [{}])[0].get("transcript", "")

                    #We now forward ALL chunks (partial and final) to the router for early interception
                    if transcript:
                        t0 = time.perf_counter()
                        
                        #Only print the final transcripts to keep the terminal clean
                        if is_final:
                            print(f"[{t0:.3f}]🔵 STT Transcript: {transcript}")
                            
                        #Push the 3-part telemetry tuple: (text, timestamp, is_final flag)
                        await token_queue.put((transcript, t0, is_final))
        except Exception as e:
            print(f"STT Receiver Error: {e}")