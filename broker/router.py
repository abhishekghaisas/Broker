import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from integrations.stt import StreamingSTT
from integrations.llm import ConstrainedLLM
from integrations.tts import DeepgramTTS
from integrations.classifier import intent_classifier 
import sqlite3

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

    audio_queue = asyncio.Queue()
    token_queue = asyncio.Queue()
    tts_queue = asyncio.Queue()
    audio_out_queue = asyncio.Queue()
    ui_queue = asyncio.Queue()


    stt_engine = StreamingSTT()
    llm_engine = ConstrainedLLM()
    tts_engine = DeepgramTTS()
    await stt_engine.connect()

    async def ui_push_task():
        try:
            while True:
                ui_data = await ui_queue.get()
                await websocket.send_json(ui_data)
        except Exception as e:
            print(f"⚠️ UI Push Task Error: {e}")

    stt_send_task = asyncio.create_task(stt_engine.process_audio(audio_queue))
    stt_recv_task = asyncio.create_task(stt_engine.receive_transcripts(token_queue))
    ui_task = asyncio.create_task(ui_push_task())

    async def process_cognition():
        early_intent_caught = False
        trigger_text = ""
        is_speaking = False 
        
        while True:
            try:
                payload = await token_queue.get() 
            
                if isinstance(payload, tuple) and len(payload) == 3:
                    text_prompt, ts, is_final = payload
                else:
                    continue 
                
                #Early Interception & Interruption Handling
                if not is_final:
                    #Queue Backpressure Fix: User started a new sentence
                    if not is_speaking:
                        print("🧹 [Router] New speech detected. Flushing remnant queues...")
                        flush_queues(tts_queue, audio_out_queue)
                        is_speaking = True

                    if not early_intent_caught:
                        fast_response = intent_classifier.predict_intent(text_prompt)
                        if fast_response:
                            print(f"🚀 [Semantic Routing] Intent caught early! Bypassing LLM.")
                            await tts_queue.put(fast_response)
                            early_intent_caught = True 
                            trigger_text = text_prompt # Save exact trigger for remainder slice
                            llm_engine.chat_history.append({"role": "user", "content": text_prompt})
                            llm_engine.chat_history.append({"role": "assistant", "content": fast_response})
                    continue 

                #Final Transcripts & Remainder Routing
                if is_final:
                    is_speaking = False # Reset speech block
                    
                    if early_intent_caught:
                        #Slice the trigger text out of the final transcript
                        remainder = text_prompt.lower().replace(trigger_text.lower(), "").strip()
                        early_intent_caught = False
                        
                        if len(remainder) > 5:
                            print(f"🔄 [Recovery] User kept talking! Routing remainder to LLM: '{remainder}'")
                            asyncio.create_task(llm_engine.generate_response(remainder, tts_queue, ui_queue))
                        else:
                            print("♻️ [Router] Ignoring final STT transcript. No trailing words detected.")
                            print("🔓 [State] early_intent_caught flag successfully RESET to False.") 
                    else:
                        asyncio.create_task(llm_engine.generate_response(text_prompt, tts_queue, ui_queue))
                        
            except Exception as e:
                print(f"[Cognition Crash] Recovering loop. Error: {e}")

    llm_task = asyncio.create_task(process_cognition())
    tts_task = asyncio.create_task(tts_engine.generate_audio(tts_queue, audio_out_queue))

    async def log_telemetry():
        while True:
            print(f"📊 [Telemetry] Audio Queue: {audio_queue.qsize()} | Token Queue: {token_queue.qsize()} | TTS Queue: {tts_queue.qsize()}")
            await asyncio.sleep(1.0)
            
    telemetry_task = asyncio.create_task(log_telemetry())

    async def send_audio_to_client():
        try:
            while True:
                audio_chunk = await audio_out_queue.get()
                await websocket.send_bytes(audio_chunk)
        except Exception as e:
            print(f"Client Playback Error: {e}")

    playback_task = asyncio.create_task(send_audio_to_client())

    try:
        while True:
            data = await websocket.receive_bytes()
            await audio_queue.put(data)
    except WebSocketDisconnect:
        print("🔴 Client disconnected.")
    except Exception as e:
        print(f"⚠️ Router Error: {e}")
    finally:
        stt_send_task.cancel()
        stt_recv_task.cancel()
        ui_task.cancel()
        llm_task.cancel()
        tts_task.cancel()
        playback_task.cancel()
        telemetry_task.cancel()
@router.get("/state")
async def get_game_state():
    try:
        conn = sqlite3.connect("game_state.db")
        cursor = conn.cursor()
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
            "puzzle": row[3]
        }
    except Exception as e:
        print(f"Backend Crash: {e}")
        raise HTTPException(status_code=500, detail=str(e))