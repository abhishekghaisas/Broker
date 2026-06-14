import asyncio
import time
import json
import re
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from db import transaction
from mcp_server import create_session, delete_session
from integrations.stt import StreamingSTT
from integrations.llm import ConstrainedLLM
from integrations.classifier import intent_classifier

router = APIRouter()

@router.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # --- 1. SESSION IDENTITY ---
    # The client generates a per-tab session id (?sid=) so concurrent players get
    # isolated game state. Sanitize to a safe key; fall back to a server id.
    raw_sid = websocket.query_params.get("sid", "")
    session_id = re.sub(r"[^A-Za-z0-9_-]", "", raw_sid)[:64] or f"sess_{uuid.uuid4().hex}"

    # Callsign arrives as ?name=; sanitize to a short plain-text label.
    raw_name = websocket.query_params.get("name", "")
    player_name = " ".join(raw_name.split()).strip()[:24] or "Operative"
    print(f"🟢 Client connected. Session {session_id[:12]}… Callsign: {player_name}")

    # --- 2. INITIALIZE QUEUES ---
    audio_queue = asyncio.Queue()
    token_queue = asyncio.Queue()
    ui_queue = asyncio.Queue()

    # --- 3. INITIALIZE ENGINES (bound to this session) ---
    stt_engine = StreamingSTT()
    llm_engine = ConstrainedLLM(player_id=session_id)
    await stt_engine.connect()

    # Create a fresh, isolated game row for this session.
    await asyncio.to_thread(create_session, session_id, player_name)

    # --- 3. DEFINE BACKGROUND TASKS ---
    async def ui_push_task():
        """Pushes JSON UI updates directly to the frontend."""
        try:
            while True:
                ui_data = await ui_queue.get()
                print(f"📤 [UI Queue] Sending {ui_data.get('type')}: {str(ui_data)[:80]}")
                try:
                    await websocket.send_json(ui_data)
                    print(f"✅ [UI Sent] {ui_data.get('type')}")
                except Exception as send_err:
                    print(f"❌ [UI Send Failed] {send_err}")
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
        cognition_start = time.perf_counter()
        print(f"🧠 [Cognition Start] Prompt: '{prompt[:50]}...'")

        classify_start = time.perf_counter()
        intent = await intent_classifier.classify(prompt)
        classify_time = time.perf_counter() - classify_start
        print(f"✅ [Classification] Intent: {intent} ({classify_time*1000:.1f}ms)")

        if intent == "ambient":
            print("🤖 [Edge Routing]: Ambient Query Detected. Bypassing LLM.")
        else:
            # Full cognitive cycle
            llm_start = time.perf_counter()
            await llm_engine.generate_response(prompt, ui_queue)
            llm_time = time.perf_counter() - llm_start
            print(f"✅ [LLM Response] Completed in {llm_time*1000:.1f}ms")

        total_time = time.perf_counter() - cognition_start
        print(f"✅ [Cognition Complete] Total: {total_time*1000:.1f}ms")

        # Drop transcripts that accumulated while we were generating/speaking.
        drain_token_queue()

    async def process_cognition():
        """Main AI evaluation loop."""
        # Accumulate STT segments and fire ONE cognition cycle per utterance.
        # End-of-utterance is detected by silence: once tokens stop arriving for
        # SILENCE_TIMEOUT seconds, fire cognition with what we have.
        # Accept both final and interim tokens to build utterance.
        SILENCE_TIMEOUT = 1.5  # seconds of silence => utterance complete
        utterance = ""
        last_token_time = time.perf_counter()
        try:
            while True:
                try:
                    # Always use silence timeout to detect end of speech
                    text, timestamp, is_final, speech_final = await asyncio.wait_for(
                        token_queue.get(), timeout=SILENCE_TIMEOUT
                    )

                    last_token_time = time.perf_counter()
                    if text.strip():
                        now = time.perf_counter()
                        latency = (now - timestamp) * 1000
                        print(f"📝 [STT Token] '{text}' (latency: {latency:.1f}ms, final: {is_final})")
                        # Accumulate both final and interim transcripts
                        utterance = f"{utterance} {text}".strip()

                except asyncio.TimeoutError:
                    # Silence detected — fire cognition with accumulated text
                    prompt, utterance = utterance, ""
                    if prompt:
                        print(f"⏱️ [Silence Timeout] Utterance ready: '{prompt[:50]}...'")
                        await fire_cognition(prompt)
                    continue

                # If speech_final arrives, immediately fire
                if speech_final and utterance:
                    prompt, utterance = utterance, ""
                    print(f"🔊 [Speech Final] Utterance ready: '{prompt[:50]}...'")
                    await fire_cognition(prompt)
        except Exception as e:
            print(f"❌ Cognition Error: {e}")

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
        # Drop this session's isolated game row so the table doesn't accumulate.
        try:
            await asyncio.to_thread(delete_session, session_id)
            print(f"🧹 Session {session_id[:12]}… cleaned up.")
        except Exception as e:
            print(f"⚠️ Session cleanup error: {e}")


# --- REST API ROUTES ---
@router.get("/state")
async def get_game_state(sid: str = ""):
    # HUD poller passes its session id; without one there's no game to report.
    if not sid:
        raise HTTPException(status_code=400, detail="Missing session id")
    try:
        with transaction() as cursor:
            cursor.execute("""
                SELECT p.health, p.credits, l.name, p.active_puzzle, p.name
                FROM players AS p
                JOIN locations AS l ON p.current_location_id = l.id
                WHERE p.id = ?
            """, (sid,))
            row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Session not found")

        return {
            "health": row[0],
            "credits": row[1],
            "location": row[2],
            "puzzle": row[3],
            "callsign": row[4],
        }
    except HTTPException:
        raise  # Don't let the generic handler mask 400/404 as a 500.
    except Exception as e:
        print(f"Backend Crash: {e}")
        raise HTTPException(status_code=500, detail=str(e))