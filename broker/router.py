import asyncio
import time
import json
import sqlite3
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from integrations.stt import StreamingSTT
from integrations.llm import ConstrainedLLM
from integrations.classifier import intent_classifier

router = APIRouter()

@router.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("🟢 Client connected to edge router.")

    # --- 1. INITIALIZE QUEUES ---
    audio_queue = asyncio.Queue()
    token_queue = asyncio.Queue()
    ui_queue = asyncio.Queue()

    # --- 2. INITIALIZE ENGINES ---
    stt_engine = StreamingSTT()
    llm_engine = ConstrainedLLM()
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

    def drain_token_queue():
        """Discards any buffered transcripts (stale duplicate finals or TTS
        self-echo that leaked into the mic) so they can't re-trigger cognition."""
        while not token_queue.empty():
            try:
                token_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def fire_cognition(prompt):
        """Runs one full classify -> LLM cognition cycle for a complete utterance."""
        intent = await intent_classifier.classify(prompt)
        if intent == "ambient":
            print("🤖 [Edge Routing]: Ambient Query Detected. Bypassing LLM.")
            # Handle ambient logic here if implemented
        else:
            # Full cognitive cycle
            await llm_engine.generate_response(prompt, ui_queue)
        # Drop transcripts that accumulated while we were generating/speaking.
        drain_token_queue()

    async def process_cognition():
        """Main AI evaluation loop."""
        # Accumulate finalized STT segments and fire ONE cognition cycle per
        # utterance. End-of-utterance is detected by a transcript silence gap:
        # the frontend VAD stops sending audio during pauses, so Deepgram never
        # sees trailing silence and rarely emits speech_final. We therefore debounce
        # — once finals stop arriving for SILENCE_TIMEOUT, the utterance is complete.
        # (speech_final, when it does arrive, fires immediately.) Firing on every
        # is_final instead would launch overlapping generations on the shared chat
        # history and repeat the response many times.
        SILENCE_TIMEOUT = 1.0  # seconds of transcript silence => utterance complete
        utterance = ""
        try:
            while True:
                try:
                    # Only impose the silence deadline once we have buffered speech.
                    timeout = SILENCE_TIMEOUT if utterance else None
                    text, timestamp, is_final, speech_final = await asyncio.wait_for(
                        token_queue.get(), timeout=timeout
                    )
                except asyncio.TimeoutError:
                    # Transcripts went quiet — the speaker paused. Fire what we have.
                    prompt, utterance = utterance, ""
                    await fire_cognition(prompt)
                    continue

                if is_final and text.strip():
                    utterance = f"{utterance} {text}".strip()

                if speech_final and utterance:
                    prompt, utterance = utterance, ""
                    await fire_cognition(prompt)
        except Exception as e:
            print(f"Cognition Error: {e}")

    async def telemetry_loop():
        """Prints background queue health metrics."""
        try:
            while True:
                print(f"📊 [Telemetry] Audio: {audio_queue.qsize()} | Tokens: {token_queue.qsize()}")
                await asyncio.sleep(5)
        except Exception:
            pass

    # --- 4. SPAWN ALL TASKS ---
    stt_send_task = asyncio.create_task(stt_engine.process_audio(audio_queue))
    stt_recv_task = asyncio.create_task(stt_engine.receive_transcripts(token_queue))
    ui_task = asyncio.create_task(ui_push_task())
    llm_task = asyncio.create_task(process_cognition())
    telemetry_task = asyncio.create_task(telemetry_loop())

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
                        # Simulate a complete STT utterance: is_final AND speech_final
                        # are both True so cognition fires exactly once.
                        await token_queue.put((user_text, time.perf_counter(), True, True))
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
        telemetry_task.cancel()


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