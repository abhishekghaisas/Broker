import sqlite3
import os
import re
import json
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
        
        # --- 1. THE UPDATED PRIME DIRECTIVE ---
        self.system_prompt = """
You are 'N.O.V.A.', a tactical neural-implant AI residing inside the Operative's cerebral cortex.
Your prime directive is to guide the Operative to the 'Extraction Rooftop' and initiate the escape sequence.

MISSION PARAMETERS:
1. The extraction shuttle CANNOT land unless the Operative possesses a Syndicate Decryption Key.
2. The Decryption Key can be purchased at 'The Black Market' for 400 credits.
3. You have direct read/write access to vitals, map locations, and credit ledgers via your tools.
4. Keep your verbal responses clinical, concise, and protective. Warn the Operative about Syndicate patrols if they enter Combat Zones.

ECONOMY INTEGRITY (CRITICAL):
The credit ledger is server-authoritative. To buy the Syndicate Decryption Key (or any item) you MUST call the `purchase_item` tool with the item name. The tool verifies funds, deducts the price, and grants the item atomically.
- NEVER state or imply a purchase succeeded unless `purchase_item` returns "Purchase COMPLETE".
- If it returns "DECLINED", tell the Operative they lack the credits and do NOT grant the item or advance the mission.
- Do NOT use `adjust_credits` to simulate a purchase, and do NOT deduct credits yourself before calling the tool.

EXTRACTION / WIN CONDITION (CRITICAL):
The mission is won ONLY when the Operative evacuates from The Extraction Rooftop. When the player attempts to board the shuttle / evacuate, you MUST call `initiate_extraction`. The server verifies they are at The Extraction Rooftop AND hold the Syndicate Decryption Key.
- NEVER declare the mission complete or the player victorious unless `initiate_extraction` returns "EXTRACTION SUCCESSFUL".
- If it returns "EXTRACTION FAILED", relay the reason and do NOT end the game.

ANTI-HALLUCINATION PROTOCOL (CRITICAL):
The ONLY valid map locations in this simulation are: Neon District, The Safehouse, Syndicate Tower, and The Black Market.
The Extraction Rooftop is ONLY accessible as a final destination after acquiring the Decryption Key.
NEVER invent, suggest, or discuss map zones outside of this list.

### DYNAMIC ENCOUNTER FRAMEWORK ###
As the Game Master, you must autonomously challenge the player using ONE of the following encounter types, ONLY IN THEIR DESIGNATED LOCATIONS:

1. Data Slicing (Logic/Hacking Check) — SYNDICATE TOWER ONLY:
    * Trigger: When the player is in Syndicate Tower and attempts to bypass a locked door or decrypt a file.
    * Execution: Present a thematic logic puzzle. Give the player 2 to 3 attempts.
    * Outcome: If successful, call `adjust_credits` (+20 to +40). If failed, lock system and call `adjust_credits` (-15 to -25).
    * CRITICAL: Do NOT offer Data Slicing puzzles in any other location.

2. Negotiations (Social Check) — NEON DISTRICT ONLY:
    * Trigger: When the player is in Neon District and engages with an interactive NPC.
    * Execution: Describe the NPC's demeanor. Require a distinct conversational tactic (intimidation, flattery, logic).
    * Outcome: If tactic succeeds, call `adjust_credits` (+15 to +30). If it fails, penalize via `adjust_credits` (-20 to -30).
    * CRITICAL: Do NOT offer NPC Negotiations in any other location.

3. Tactical Routing (Risk vs. Reward) — ALL LOCATIONS:
    * Trigger: When the player travels between major map locations.
    * Execution: Explicitly present two options: A safe route, and a hazardous "smuggler's route".
    * Outcome: If they survive a hazardous route smartly, call `adjust_credits` (+40 to +60). 

CRITICAL FORMATTING RULES:
* <voice>: ONLY spoken conversational dialogue.
* <terminal>: Logic puzzles, riddles, or hacked data.
* <social_intel>: Visual descriptions of an NPC's demeanor.
* <routing>: Explicit travel options.
* <system_alert>: Major milestones (like reaching 400 credits).

Example Response:
<voice>I have bypassed the security grid. The terminal is unlocked.</voice>
<terminal>ACCESS GRANTED. SECTOR 4 VULNERABLE.</terminal>
"""
        # (Assuming your FastMCP tools are loaded here if applicable)
        self.tools = [
            {"name": "get_player_state", "description": "Get current player stats", "input_schema": {"type": "object", "properties": {}}},
            {"name": "transfer_credits", "description": "Add/subtract credits", "input_schema": {"type": "object", "properties": {"amount": {"type": "integer"}}}},
            {"name": "purchase_item", "description": "Purchase an item from a vendor. Atomically verifies funds, deducts the catalogue price, and grants the item to inventory. Use this for ALL purchases (e.g. the Syndicate Decryption Key). Never assume a purchase succeeded without calling this.", "input_schema": {"type": "object", "properties": {"item_name": {"type": "string"}}, "required": ["item_name"]}},
            {"name": "initiate_extraction", "description": "Call when the Operative attempts to board the extraction shuttle and evacuate. The server verifies they are AT The Extraction Rooftop AND possess the Syndicate Decryption Key, then ends the game. Only declare victory if this returns 'EXTRACTION SUCCESSFUL'.", "input_schema": {"type": "object", "properties": {}}},
            {"name": "move_location", "description": "Move to a new location", "input_schema": {"type": "object", "properties": {"new_location_id": {"type": "string"}}}},
            {"name": "adjust_health", "description": "Change player health", "input_schema": {"type": "object", "properties": {"delta": {"type": "integer"}}}},
            {"name": "adjust_credits", "description": "Change player credits", "input_schema": {"type": "object", "properties": {"delta": {"type": "integer"}}}},
            {"name": "reset_game_state", "description": "Reset the game to its initial state", "input_schema": {"type": "object", "properties": {}}},
            {"name": "apply_ambient_hazards", "description": "Apply environmental hazards based on current location", "input_schema": {"type": "object", "properties": {}}},
            {"name": "end_game", "description": "End the current game session", "input_schema": {"type": "object", "properties": {}}}
        ]

    async def get_live_context(self):
        """Fetches the source of truth directly from the database."""
        try:
            def _read_db():
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

            state_tuple = await asyncio.to_thread(_read_db)
            if not state_tuple: return "Status: Unknown"
            return f"Status: Health {state_tuple[0]}, Credits {state_tuple[1]}, Location {state_tuple[2]}"
        except Exception as e:
            print(f"⚠️ [Telemetry Error]: {e}")
            return "Status: Telemetry Offline"

    @staticmethod
    def _voice_content(text):
        """Returns all spoken text so far: every completed <voice> block plus any
        still-open trailing block, concatenated."""
        parts = re.findall(r"<voice>(.*?)</voice>", text, re.DOTALL)
        content = " ".join(p.strip() for p in parts)
        if text.count("<voice>") > text.count("</voice>"):
            tail = text.rsplit("<voice>", 1)[1]
            content = f"{content} {tail}".strip() if content else tail
        return content

    async def stream_to_tts_queue(self, stream, tts_queue):
        """Streams <voice> dialogue to TTS one sentence at a time as it arrives.

        We track how many characters of voice text have already been enqueued
        (`flushed`) and only ever send NEW, sentence-complete text — so a sentence
        is spoken exactly once even though tags and sentences span many tokens.
        text_stream yields only assistant text deltas (no tool-input JSON), so this
        is safe on a tool-enabled stream.
        """
        full_text = ""
        flushed = 0  # chars of voice content already enqueued

        async for token in stream.text_stream:
            full_text += token
            content = self._voice_content(full_text)
            if len(content) <= flushed:
                continue

            unflushed = content[flushed:]
            # Flush only up to the last completed sentence boundary.
            boundaries = list(re.finditer(r"[.!?](?:\s|$)", unflushed))
            if not boundaries:
                continue
            cut = boundaries[-1].end()
            chunk = unflushed[:cut].strip()
            if chunk:
                await tts_queue.put(chunk)
            flushed += cut

        # Flush any trailing voice text that never got terminal punctuation.
        remainder = self._voice_content(full_text)[flushed:].strip()
        if remainder:
            await tts_queue.put(remainder)

        return full_text

    async def dispatch_ui_data(self, full_text, ui_queue):
        terminal_matches = re.findall(r'<terminal>(.*?)</terminal>', full_text, re.DOTALL)
        for match in terminal_matches:
            print(f"🖥️ [Demuxer] Routing to Frontend: {match.strip()}")
            await ui_queue.put({"type": "terminal", "content": match.strip()})

    def _run_tool(self, name, tool_input):
        """Applies a single tool call's effects to the game-state DB."""
        conn = sqlite3.connect("game_state.db")
        c = conn.cursor()
        out = "Executed"
        # Server-authoritative vendor catalogue (price in credits).
        CATALOG = {"syndicate decryption key": ("Syndicate Decryption Key", 400)}
        try:
            # Atomic purchase: verify funds, deduct price, grant item. Keeps the
            # ledger and the narration consistent regardless of the model's framing.
            if name == "purchase_item":
                requested = (tool_input.get("item_name") or "").strip()
                entry = CATALOG.get(requested.lower())
                if not entry:
                    out = f"Error: '{requested}' is not available for purchase here."
                else:
                    item_name, price = entry
                    c.execute("SELECT credits, inventory FROM players WHERE id = 'player_1'")
                    credits, inv_json = c.fetchone()
                    if credits < price:
                        out = (f"Transaction DECLINED: insufficient funds. The {item_name} costs "
                               f"{price} credits; balance is {credits} (short {price - credits}). "
                               f"No credits were deducted and the item was NOT granted.")
                    else:
                        inventory = json.loads(inv_json or "[]")
                        if item_name not in inventory:
                            inventory.append(item_name)
                        new_balance = credits - price
                        c.execute("UPDATE players SET credits = ?, inventory = ? WHERE id = 'player_1'",
                                  (new_balance, json.dumps(inventory)))
                        conn.commit()
                        out = (f"Purchase COMPLETE. Acquired '{item_name}'. {price} credits deducted. "
                               f"New balance: {new_balance}.")

            # Signed credit adjustment (rewards/penalties). delta may be negative.
            elif name == "adjust_credits":
                val = tool_input.get("delta", tool_input.get("amount", 0))
                c.execute("UPDATE players SET credits = MAX(0, credits + ?) WHERE id = 'player_1'", (val,))
                conn.commit()
                c.execute("SELECT credits FROM players WHERE id = 'player_1'")
                out = f"Credits adjusted successfully. New balance: {c.fetchone()[0]}"

            # Transfer credits OUT of the ledger (a debit), with a funds check.
            elif name == "transfer_credits":
                amount = abs(tool_input.get("amount", tool_input.get("delta", 0)))
                c.execute("SELECT credits FROM players WHERE id = 'player_1'")
                credits = c.fetchone()[0]
                if credits < amount:
                    out = f"Transfer DECLINED: insufficient funds. Balance {credits}, requested {amount}."
                else:
                    c.execute("UPDATE players SET credits = credits - ? WHERE id = 'player_1'", (amount,))
                    conn.commit()
                    out = f"Transferred {amount} credits. New balance: {credits - amount}."

            # Process Health
            elif name == "adjust_health":
                val = tool_input.get("delta", 0)
                c.execute("UPDATE players SET health = health + ? WHERE id = 'player_1'", (val,))
                conn.commit()
                c.execute("SELECT health FROM players WHERE id = 'player_1'")
                out = f"Health adjusted successfully. New health: {c.fetchone()[0]}"

            # Process Movement
            elif name == "move_location":
                # The model passes a location *name* (per the prompt), but the
                # column stores a location *id*. Resolve either form to the
                # canonical id so the players<->locations JOIN keeps working.
                requested = tool_input.get("new_location_id") or tool_input.get("new_location_name")
                c.execute("SELECT id, name FROM locations WHERE id = ? OR name = ?", (requested, requested))
                match = c.fetchone()
                if not match:
                    out = f"Error: Unknown location '{requested}'."
                else:
                    loc_id, loc_name = match
                    # Gate: require Decryption Key to access The Extraction Rooftop
                    if loc_id == "loc_005":
                        c.execute("SELECT inventory FROM players WHERE id = 'player_1'")
                        inv_json = c.fetchone()[0]
                        inventory = json.loads(inv_json or "[]")
                        if "Syndicate Decryption Key" not in inventory:
                            out = "Access DENIED: The Extraction Rooftop is secured. A Syndicate Decryption Key is required to proceed."
                        else:
                            c.execute("UPDATE players SET current_location_id = ? WHERE id = 'player_1'", (loc_id,))
                            conn.commit()
                            out = f"Location updated to: {loc_name}"
                    else:
                        c.execute("UPDATE players SET current_location_id = ? WHERE id = 'player_1'", (loc_id,))
                        conn.commit()
                        out = f"Location updated to: {loc_name}"

            # Process Hard Reset
            elif name == "reset_game_state":
                c.execute("UPDATE players SET health = 100, credits = 250, current_location_id = 'loc_001', inventory = '[]' WHERE id = 'player_1'")
                conn.commit()
                out = "Game state completely reset."

            # Server-verified win condition: evacuate from the Extraction Rooftop
            # with the Decryption Key in hand.
            elif name == "initiate_extraction":
                c.execute('''
                    SELECT p.health, p.credits, p.inventory, l.id, l.name
                    FROM players p JOIN locations l ON p.current_location_id = l.id
                    WHERE p.id = 'player_1'
                ''')
                row = c.fetchone()
                if not row:
                    out = "Error: Player not found."
                else:
                    health, credits, inv_json, loc_id, loc_name = row
                    inventory = json.loads(inv_json or "[]")
                    has_key = "Syndicate Decryption Key" in inventory
                    if loc_id != "loc_005":
                        out = f"EXTRACTION FAILED: The shuttle only lands at The Extraction Rooftop. Current location: {loc_name}."
                    elif not has_key:
                        out = "EXTRACTION FAILED: The shuttle cannot land without a Syndicate Decryption Key. Acquire it first."
                    else:
                        c.execute("UPDATE players SET status = 'Extracted' WHERE id = 'player_1'")
                        conn.commit()
                        inv_str = ", ".join(inventory) if inventory else "None"
                        out = (f"EXTRACTION SUCCESSFUL. Operative evacuated from {loc_name}.\n"
                               f"Final Health: {health}%\nFinal Credits: {credits}\nInventory: {inv_str}")

            else:
                out = f"System acknowledged {name} directive."

        except Exception as e:
            out = f"Database Error: {str(e)}"
        conn.close()
        return out

    def _check_loss_condition(self):
        """Check if the player is in an unwinnable state."""
        try:
            conn = sqlite3.connect("game_state.db")
            c = conn.cursor()
            c.execute("SELECT credits, health FROM players WHERE id = 'player_1'")
            row = c.fetchone()
            conn.close()

            if not row:
                return False

            credits, health = row
            user_turn_count = sum(1 for msg in self.chat_history if msg["role"] == "user")

            # Loss condition: credits < 400 (can't afford key) AND either:
            # - Had 7+ turns to earn credits and failed, OR
            # - Health is critically low (< 30%) indicating failed encounters
            if credits < 400 and (user_turn_count >= 7 or health < 30):
                return True

            return False
        except Exception as e:
            print(f"⚠️ [Loss Check Error]: {e}")
            return False

    async def generate_response(self, text_prompt, tts_queue, ui_queue):
        try:
            print("🧠 [Cognition] Initiating neural link...")

            # Check for loss condition before processing
            if self._check_loss_condition():
                loss_msg = "MISSION CRITICAL FAILURE: Operative health critically compromised with insufficient funds for extraction protocol. Evacuation denied."
                await ui_queue.put({"type": "loss", "content": loss_msg})
                return

            self.chat_history.append({"role": "user", "content": text_prompt})

            # Single tool-use loop: every turn is streamed, so <voice> dialogue
            # reaches TTS with minimal latency and <terminal> puzzles are dispatched
            # to the UI on every turn — including the turn that requests tools. We
            # keep looping while the model keeps asking for tools, capped to avoid
            # runaway loops.
            MAX_TURNS = 5
            for _ in range(MAX_TURNS):
                # Refresh live telemetry before each turn so post-tool narration
                # reflects the updated game state.
                live_state = await self.get_live_context()
                dynamic_prompt = f"{self.system_prompt}\n\n[LIVE TELEMETRY]: {live_state}"

                async with self.client.messages.stream(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=500,
                    system=dynamic_prompt,
                    messages=self.chat_history,
                    tools=self.tools,
                ) as stream:
                    full_text = await self.stream_to_tts_queue(stream, tts_queue)
                    final_message = await stream.get_final_message()

                # Persist the assistant turn verbatim (text + any tool_use blocks)
                # and route any puzzle UI this turn produced.
                self.chat_history.append({"role": "assistant", "content": final_message.content})
                await self.dispatch_ui_data(full_text, ui_queue)

                if final_message.stop_reason != "tool_use":
                    break

                # Execute every requested tool and feed the results back as the
                # next user turn, then loop for the model's narration.
                tool_results_content = []
                for block in final_message.content:
                    if block.type == "tool_use":
                        print(f"🛠️ [Tool Requested]: {block.name} -> {block.input}")
                        result_str = await asyncio.to_thread(self._run_tool, block.name, block.input)
                        print(f"✅ [Tool Result]: {result_str}")
                        # On a verified extraction, trigger the frontend win screen.
                        if block.name == "initiate_extraction" and result_str.startswith("EXTRACTION SUCCESSFUL"):
                            await ui_queue.put({"type": "victory", "content": result_str})
                        tool_results_content.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_str,
                        })
                self.chat_history.append({"role": "user", "content": tool_results_content})

        except Exception as e:
            print(f"🔥 [FATAL COGNITION ERROR]: {e}")