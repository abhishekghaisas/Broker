import asyncio
import time
import json
import sqlite3
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from integrations.stt import StreamingSTT
from integrations.llm import ConstrainedLLM
from integrations.tts import DeepgramTTS
from integrations.classifier import intent_classifier 

router = APIRouter()

def flush_queues(tts_queue, audio_out_queue):
    """Instantly purges all remnant data to prepare for a fresh query."""
    while not tts_queue.empty():
        try:
            tts_queue.get_nowait()
            tts_queue.task_done()
        except asyncio.QueueEmpty:
            break
    while not audio_out_queue.empty():
        try:
            audio_out_queue.get_nowait()
            audio_out_queue.task_done()
        except asyncio.QueueEmpty:
            break

@router.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("🟢 Client connected to edge router.")

    # --- 1. INITIALIZE QUEUES ---
    audio_queue = asyncio.Queue()
    token_queue = asyncio.Queue()
    tts_queue = asyncio.Queue(maxsize=10) # Queue backpressure applied
    audio_out_queue = asyncio.Queue()
    ui_queue = asyncio.Queue()

    # --- 2. INITIALIZE ENGINES ---
    stt_engine = StreamingSTT()
    llm_engine = ConstrainedLLM()
    tts_engine = DeepgramTTS()
    await stt_engine.connect()

    # --- 3. DEFINE BACKGROUND TASKS ---
    async def ui_push_task():
        """Pushes JSON UI updates directly to the frontend."""
        try:
            while True:
                ui_data = await ui_queue.get()
                await websocket.send_json(ui_data)
        except Exception as e:
            print(f"⚠️ UI Push Task Error: {e}")

    async def process_cognition():
        """Main AI evaluation loop."""
        try:
            while True:
                text, timestamp, is_final = await token_queue.get()
                if is_final and text.strip():
                    flush_queues(tts_queue, audio_out_queue)
                    
                    # Intent classifier routing
                    intent = await intent_classifier.classify(text)
                    if intent == "ambient":
                        print("🤖 [Edge Routing]: Ambient Query Detected. Bypassing LLM.")
                        # Handle ambient logic here if implemented
                        pass
                    else:
                        # Full cognitive cycle
                        await llm_engine.generate_response(text, tts_queue, ui_queue)
        except Exception as e:
            print(f"Cognition Error: {e}")

    async def telemetry_loop():
        """Prints background queue health metrics."""
        try:
            while True:
                print(f"📊 [Telemetry] Audio: {audio_queue.qsize()} | Tokens: {token_queue.qsize()} | TTS: {tts_queue.qsize()}")
                await asyncio.sleep(5)
        except Exception:
            pass

    async def send_audio_to_client():
        """Streams TTS binary bytes to frontend for immediate playback."""
        try:
            while True:
                audio_chunk = await audio_out_queue.get()
                await websocket.send_bytes(audio_chunk)
        except Exception as e:
            print(f"Client Playback Error: {e}")

    # --- 4. SPAWN ALL TASKS ---
    stt_send_task = asyncio.create_task(stt_engine.process_audio(audio_queue))
    stt_recv_task = asyncio.create_task(stt_engine.receive_transcripts(token_queue))
    ui_task = asyncio.create_task(ui_push_task())
    llm_task = asyncio.create_task(process_cognition())
    tts_task = asyncio.create_task(tts_engine.generate_audio(tts_queue, audio_out_queue))
    telemetry_task = asyncio.create_task(telemetry_loop())
    playback_task = asyncio.create_task(send_audio_to_client())

    # --- 5. WEBSOCKET DEMUXING LOOP ---
    try:
        while True:
            # Receive handles both text and binary frames dynamically
            message = await websocket.receive()
            
            # AUDIO PLANE (VAD Chunks from Microphone)
            if "bytes" in message:
                await audio_queue.put(message["bytes"])
                
            # DATA PLANE (Keyboard Input / UI Events)
            elif "text" in message:
                try:
                    data = json.loads(message["text"])
                    if data.get("type") == "text_input":
                        user_text = data.get("text")
                        print(f"⌨️ [Manual Input Intercept]: {user_text}")
                        
                        # INJECT DIRECTLY INTO COGNITION (Bypass STT entirely)
                        # We simulate an STT final transcript: (text, timestamp, is_final)
                        await token_queue.put((user_text, time.perf_counter(), True))
                except Exception as e:
                    print(f"⚠️ Text Parse Error: {e}")

    except WebSocketDisconnect:
        print("🔴 Client disconnected.")
    except Exception as e:
        print(f"⚠️ Router Error: {e}")
    finally:
        # --- 6. CLEANUP ---
        stt_send_task.cancel()
        stt_recv_task.cancel()
        ui_task.cancel()
        llm_task.cancel()
        tts_task.cancel()
        telemetry_task.cancel()
        playback_task.cancel()


# --- REST API ROUTES ---
@router.get("/state")
async def get_game_state():
    try:
        conn = sqlite3.connect("game_state.db")
        cursor = conn.cursor()
        # Querying the exact 4 data columns including the active_puzzle
        query = """
            SELECT p.health, p.credits, l.name, p.active_puzzle 
            FROM players AS p
            JOIN locations AS l ON p.current_location_id = l.id
            WHERE p.id = 'player_1'
        """
        cursor.execute(query)
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Player not found")
            
        return {
            "health": row[0],
            "credits": row[1],
            "location": row[2],
            "puzzle": row[3] # Index 3 now maps correctly to the DB pull
        }
    except Exception as e:
        print(f"Backend Crash: {e}")
        raise HTTPException(status_code=500, detail=str(e))