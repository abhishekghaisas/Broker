import sqlite3
import os
import re
import asyncio
from anthropic import AsyncAnthropic
# Import tools and physics from the server file
from mcp_server import (
    get_player_state, 
    transfer_credits, 
    move_location, 
    grant_item, 
    reset_game_state, 
    adjust_credits, 
    adjust_health, 
    apply_ambient_hazards,
    end_game
)

class ConstrainedLLM:
    def __init__(self):
        self.client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.chat_history = []
        self.system_prompt = """
            You are 'N.O.V.A.', a tactical neural-implant AI residing inside the Operative's cerebral cortex.
            Your prime directive is to guide the Operative to the 'Extraction Rooftop' and initiate the escape sequence.

            MISSION PARAMETERS:
            1. The extraction shuttle CANNOT land unless the Operative possesses a Syndicate Decryption Key.
            2. The Decryption Key can be purchased at 'The Black Market' for 400 credits.
            3. You have direct read/write access to vitals, map locations, and credit ledgers via your tools.
            4. Keep your verbal responses clinical, concise, and protective. Warn the Operative about Syndicate patrols if they enter Combat Zones.
            
            ANTI-HALLUCINATION PROTOCOL (CRITICAL):
            The ONLY valid map locations in this simulation are: Neon District, The Safehouse, Syndicate Tower, and The Black Market. 
            NEVER invent, suggest, or discuss locations outside of these four map sectors.

            ### DYNAMIC ENCOUNTER FRAMEWORK ###
            As the Game Master, you must autonomously challenge the player using ONE of the following encounter types:

            1. Data Slicing (Logic/Hacking Check):
            * Trigger: When the player attempts to bypass a locked door or decrypt a file.
            * Execution: Present a thematic logic puzzle. Give the player 2 to 3 attempts.
            * Outcome: If successful, call `adjust_credits` (+20 to +40). If failed, lock system and call `adjust_credits` (-15 to -25).

            2. Negotiations (Social Check):
            * Trigger: When the player engages with an interactive NPC.
            * Execution: Describe the NPC's demeanor. Require a distinct conversational tactic (intimidation, flattery, logic).
            * Outcome: If tactic succeeds, call `adjust_credits` (+15 to +30). If it fails, penalize via `adjust_credits` (-20 to -30).

            3. Tactical Routing (Risk vs. Reward):
            * Trigger: When the player travels between major map locations.
            * Execution: Explicitly present two options: A safe route, and a hazardous "smuggler's route".
            * Outcome: If they survive a hazardous route smartly, call `adjust_credits` (+40 to +60). 

            ### STRICT OUTPUT SKELETON ###
            Format EVERY response using these XML tags to separate spoken dialogue from UI data:
            * <voice>: ONLY spoken conversational dialogue.
            * <terminal>: Logic puzzles, riddles, or hacked data.
            * <social_intel>: Visual descriptions of an NPC's demeanor.
            * <routing>: Explicit travel options.
            * <system_alert>: Major milestones (like reaching 400 credits).
        """
        
        self.tools = [
            {"name": "get_player_state", "description": "Get current player stats", "input_schema": {"type": "object", "properties": {}}},
            {"name": "transfer_credits", "description": "Add/subtract credits", "input_schema": {"type": "object", "properties": {"amount": {"type": "integer"}}}},
            {"name": "move_location", "description": "Move to a new location", "input_schema": {"type": "object", "properties": {"new_location_id": {"type": "string"}}}},
            {"name": "adjust_health", "description": "Change player health", "input_schema": {"type": "object", "properties": {"delta": {"type": "integer"}}}},
            {"name": "adjust_credits", "description": "Change player credits", "input_schema": {"type": "object", "properties": {"delta": {"type": "integer"}}}},
            {"name": "reset_game_state", "description": "Reset the game to its initial state", "input_schema": {"type": "object", "properties": {}}},
            {"name": "apply_ambient_hazards", "description": "Apply environmental hazards based on current location", "input_schema": {"type": "object", "properties": {}}},
            {"name": "end_game", "description": "End the current game session", "input_schema": {"type": "object", "properties": {}}}
        ]

    async def stream_to_tts_queue(self, stream, tts_queue):
        """
        State Machine: Only queues tokens for TTS if inside <voice> tags.
        Returns the full text accumulated for UI parsing.
        """
        full_text = ""
        in_voice_tag = False
        
        async for chunk in stream:
            if chunk.type == "content_block_delta":
                token = chunk.delta.text
                full_text += token
                
                #State Machine Logic
                if "<voice>" in full_text:
                    in_voice_tag = True
                
                if in_voice_tag:
                    #Strip the voice tag itself before queuing
                    clean_token = token.replace("<voice>", "").replace("</voice>", "")
                    await tts_queue.put(clean_token)
                    
                if "</voice>" in full_text:
                    in_voice_tag = False
                    
        return full_text
    
    async def get_live_context(self):
        """Fetches the source of truth directly from the database, bypassing MCP wrappers."""
        try:
            #Define a synchronous DB read
            def _read_db():
                import sqlite3
                conn = sqlite3.connect("game_state.db")
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT p.health, p.credits, l.name 
                    FROM players p
                    JOIN locations l ON p.current_location_id = l.id
                    WHERE p.id = 'player_1'
                ''')
                row = cursor.fetchone()
                conn.close()
                return row

            #Offload the read to a background thread to preserve sub-500ms latency
            state_tuple = await asyncio.to_thread(_read_db)
            
            if not state_tuple: 
                return "Status: Unknown"
            
            return f"Status: Health {state_tuple[0]}, Credits {state_tuple[1]}, Location {state_tuple[2]}"
            
        except Exception as e:
            print(f"⚠️ [Telemetry Error]: {e}")
            return "Status: Telemetry Offline"

    async def generate_response(self, text_prompt, tts_queue, ui_queue):
        """
        Main cognitive loop: Orchestrates tool use, streaming, and UI dispatch.
        """
        self.chat_history.append({"role": "user", "content": text_prompt})

        live_state = await self.get_live_context()

        dynamic_prompt = f"{self.system_prompt}\n\n[LIVE TELEMETRY]: {live_state}"
        
        #Initial request to LLM
        response = await self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=self.system_prompt,
            messages=self.chat_history,
            tools=self.tools
        )
        
        #Stream Narrative
        stream = await self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=dynamic_prompt,
            messages=self.chat_history,
            stream=True
        )
        
        final_text = await self.stream_to_tts_queue(stream, tts_queue)
        
        #Dispatch non-voice data to UI
        await self.dispatch_ui_data(final_text, ui_queue)
        
        self.chat_history.append({"role": "assistant", "content": final_text})

    async def dispatch_ui_data(self, text, ui_queue):
        ui_tags = ['terminal', 'social_intel', 'routing', 'system_alert']
        for tag in ui_tags:
            matches = re.findall(f'<{tag}>(.*?)</{tag}>', text, re.DOTALL)
            for content in matches:
                await ui_queue.put({"type": tag, "content": content.strip()})

llm_engine = ConstrainedLLM()