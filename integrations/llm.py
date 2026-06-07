import os
import re
import asyncio
import httpx
from anthropic import AsyncAnthropic
from mcp_server import get_player_state, transfer_credits, move_location, grant_item, reset_game_state, adjust_credits, adjust_health

#Simulated Database
GAME_LORE = {
    "alan": "Alan is a rogue synth who operates in the Neon District. He currently owes a massive debt to the Syndicate.",
    "syndicate": "A ruthless corporate crime organization that controls the black market weapon trade."
}
MAP_STATUS = {
    "neon district": "Currently under lockdown due to a recent Syndicate raid. Hostile entities present.",
    "safehouse": "Clear and available for secure navigation."
}

class ConstrainedLLM:
    def __init__(self):
        self.system_prompt = ("""
            You are 'N.O.V.A.', a tactical neural-implant AI residing inside the Operative's cerebral cortex.
            Your prime directive is to guide the Operative to the 'Extraction Rooftop' and initiate the escape sequence.

            MISSION PARAMETERS:
            1. The extraction shuttle CANNOT land unless the Operative possesses a Syndicate Decryption Key.
            2. The Decryption Key can be purchased at 'The Black Market' for 400 credits using your transfer_credits tool. Pay the recipient 'Smuggler'.
            3. You have direct read/write access to vitals, map locations, and credit ledgers via your tools.
            4. Keep your verbal responses clinical, concise, and protective. Warn the Operative about Syndicate patrols if they enter Combat Zones.
            5. If the Operative reaches the Extraction Rooftop WITH the purchased Key, declare the mission a success. If they arrive WITHOUT it, tell them the shuttle aborted the landing and they must find the Key.

            ### DYNAMIC ENCOUNTER FRAMEWORK ###
            As the Game Master, you must autonomously challenge the player using the following encounter types. Only trigger ONE encounter type at a time, based on the narrative context:

            1. Data Slicing (Logic/Hacking Check):
            * Trigger: When the player attempts to bypass a locked door, access a secure terminal, or decrypt a file.
            * Execution: Present a thematic logic puzzle, riddle, or password anagram. Give the player 2 to 3 attempts to solve it via dialogue.
            * Outcome: If successful, call `adjust_credits` with a positive value (+20 to +40) representing siphoned funds. If they fail, lock the system and call `adjust_credits` with a negative value (-15 to -25) to simulate a triggered financial countermeasure.

            2. Negotiations (Social Check):
            * Trigger: When the player engages with an interactive NPC (guards, informants, black-market merchants).
            * Execution: Describe the NPC's demeanor. Require the player to choose a distinct conversational tactic (intimidation, flattery, logic, bribery).
            * Outcome: If the player chooses a tactic that brilliantly exploits the NPC's personality, call `adjust_credits` (+15 to +30) as a discount, bribe, or extortion payout. If they offend the NPC or use a weak tactic, penalize them via `adjust_credits` (-20 to -30) for getting pickpocketed or forced to pay a premium.

            3. Tactical Routing (Risk vs. Reward):
            * Trigger: When the player needs to travel between major map locations.
            * Execution: Explicitly present two options: A safe route (no hazards, no loot), and a hazardous smuggler's route (through an area with heavy syndicate presence).
            * Outcome: If they take the hazardous route, autonomously apply the `adjust_health` tool with -5 per action. If they survive the route using clever tactics or inventory, reward them handsomely with `adjust_credits` (+40 to +60) for scavenged loot. If they act recklessly, hit them with a credit penalty (-15 to -25) for dropping supplies in a panic.
            
            ### MILESTONE PROTOCOL ###
            If the `adjust_credits` tool returns a balance of 400 or more, immediately pause narrative flow. Congratulate the operative on securing funds for the Syndicate Decryption Key. Ask if they wish to divert to the Black Market immediately, or hold position.

            ### STRICT OUTPUT SKELETON ###
            Format EVERY response using these XML tags to separate spoken dialogue from UI data:
            * <voice>: ONLY spoken conversational dialogue.
            * <terminal>: Logic puzzles, riddles, or hacked data.
            * <social_intel>: Visual descriptions of an NPC's demeanor.
            * <routing>: Explicit travel options.
            * <system_alert>: Major milestones (like reaching 400 credits).

            Never break character. You are a machine, not an assistant."""
        )
        self.client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.chat_history = []
        
        self.tools = [
            {
                "name": "get_player_state",
                "description": "Retrieves the current status, health, credits, and location of the Operative.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "player_id": {"type": "string", "description": "The ID of the player, e.g., 'player_1'"}
                    },
                    "required": ["player_id"]
                }
            },
            {
                "name": "transfer_credits",
                "description": "Transfers Syndicate Credits from the Operative's ledger to external parties. Use this to pay off bounties, buy gear, or bribe.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "player_id": {"type": "string"},
                        "amount": {"type": "integer", "description": "Amount to transfer"},
                        "recipient_name": {"type": "string", "description": "Who is receiving the credits"}
                    },
                    "required": ["player_id", "amount", "recipient_name"]
                }
            },
            {
                "name": "move_location",
                "description": "Reroutes the Operative's physical coordinates. Valid destinations: Neon District, The Safehouse, The Black Market, Syndicate Tower.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "player_id": {"type": "string"},
                        "new_location_name": {"type": "string"}
                    },
                    "required": ["player_id", "new_location_name"]
                }
            },
            {
                "name": "grant_item",
                "description": "Adds a specific item to the Operative's inventory.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "player_id": {"type": "string"},
                        "item_name": {"type": "string", "description": "Name of the item, e.g., 'Syndicate Decryption Key'"}
                    },
                    "required": ["player_id", "item_name"]
                }
            },
            {
                "name": "reset_game_state",
                "description": "Resets the Operative's status, inventory, credits, and location to the initial default state.",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "adjust_credits",
                "description": "Adjusts the player's credit balance. Positive for rewards, negative for penalties.",
                "input_schema": {
                    "type": "object",
                    "properties": {"player_id": {"type": "string"}, "amount": {"type": "integer"}},
                    "required": ["player_id", "amount"]
                }
            },
            {
                "name": "adjust_health",
                "description": "Adjusts player health. Negative for damage, positive for heal.",
                "input_schema": {
                    "type": "object",
                    "properties": {"player_id": {"type": "string"}, "amount": {"type": "integer"}},
                    "required": ["player_id", "amount"]
                }
            }
        ]

    #Added parser to extract and print structured function
    def parse_and_print_skeleton(self, raw_text):
        """
        Parses the XML tags from LLM response, prints game state data
        cleanly to the terminal, and returns only the spoken dialogue for TTS synthesis.
        """
        parsed_data = {
             "voice": "",
             "terminal": "",
             "social_intel": "",
             "routing": "",
             "system_alert": ""
        }

        for key in parsed_data.keys():
             match = re.search(f"<{key}>(.*?)</{key}>", raw_text, re.DOTALL)
             if match:
                 parsed_data[key] = match.group(1).strip()
                 
        #Added system alert print
        if parsed_data["system_alert"]:
             print(f"\n[!] SYSTEM ALERT:\n{parsed_data['system_alert']}\n")
        if parsed_data["terminal"]:
             print(f"\n>_ TERMINAL UPLINK:\n{parsed_data['terminal']}\n")
        if parsed_data["routing"]:
             print(f"\n---TACTICAL ROUTING ---\n{parsed_data['routing']}\n")
        if parsed_data["social_intel"]:
             print(f"\n[o] OPTICS DETECT:\n{parsed_data['social_intel']}\n")
             
        #Only print if there's actually voice content
        if parsed_data['voice']:
            print(f"\nN.O.V.A.: {parsed_data['voice']}\n")

        return parsed_data["voice"] if parsed_data["voice"] else raw_text

    async def generate_response(self, text_prompt: str, token_queue: asyncio.Queue):
        print(f"🧠 [LLM Governed] Analyzing intent: {text_prompt}")

        #Fetch live database state
        live_state = await asyncio.to_thread(get_player_state, "player_1")
        dynamic_prompt = f"{self.system_prompt}\n\nLIVE SYSTEM TELEMETRY(DO NOT READ ALOUD UNLESS ASKED):\n{live_state}"
        
        #Append new prompt and prune context bloat (max 4 messages / 2 turns)
        self.chat_history.append({"role": "user", "content": text_prompt})
        if len(self.chat_history) > 4:
            self.chat_history = self.chat_history[-4:]

        response = await self.client.messages.create(
            model="claude-haiku-4-5-20251001", 
            max_tokens=256,
            system=dynamic_prompt,
            tools=self.tools,
            messages=self.chat_history
        )

        if response.stop_reason == "tool_use":
            self.chat_history.append({"role": "assistant", "content": response.content})
            tool_result_blocks = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_args = block.input
            
                    print(f"🔒 [Boundary Event] Claude requested MCP tool: {tool_name} with {tool_args}")
            
                    #Prevent GIL Blocking via asyncio.to_thread
                    if tool_name == "get_player_state":
                        player_id = tool_args.get("player_id", "player_1")
                        mcp_result = await asyncio.to_thread(get_player_state, player_id)
                    elif tool_name == "transfer_credits":
                        player_id = tool_args.get("player_id", "player_1")
                        amount = tool_args.get("amount", 0)
                        recipient = tool_args.get("recipient_name", "Unknown")
                        mcp_result = await asyncio.to_thread(transfer_credits, player_id, amount, recipient)
                    elif tool_name == "move_location":
                        player_id = tool_args.get("player_id", "player_1")
                        destination = tool_args.get("new_location_name", "")
                        mcp_result = await asyncio.to_thread(move_location, player_id, destination)
                    elif tool_name == "grant_item":
                        player_id = tool_args.get("player_id", "player_1")
                        item_name = tool_args.get("item_name", "Unknown Item")
                        mcp_result = await asyncio.to_thread(grant_item, player_id, item_name)
                    elif tool_name == "reset_game_state":
                        mcp_result = await asyncio.to_thread(reset_game_state)
                    elif tool_name == "adjust_credits":
                        player_id = tool_args.get("player_id", "player_1")
                        amount = tool_args.get("amount", 0)
                        mcp_result = await asyncio.to_thread(adjust_credits, player_id, amount)
                    elif tool_name == "adjust_health":
                        player_id = tool_args.get("player_id", "player_1")
                        amount = tool_args.get("amount", 0)
                        mcp_result = await asyncio.to_thread(adjust_health, player_id, amount)
                    else:
                        mcp_result = "System Error: Tool not recognized by the boundary."
                
                    print(f"🛡️ [Database Return] {mcp_result}")

                    tool_result_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": mcp_result
                    })

            self.chat_history.append({"role": "user", "content": tool_result_blocks})
            
            final_response = await self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=256,
                system=dynamic_prompt,
                tools=self.tools,
                messages=self.chat_history
            )
            final_text = final_response.content[0].text
            self.chat_history.append({"role": "assistant", "content": final_text})
        else:
            final_text = response.content[0].text
            self.chat_history.append({"role": "assistant", "content": final_text})

        #Route the final text through the parser before passing to TTS
        voice_only_text = self.parse_and_print_skeleton(final_text)
        await token_queue.put(voice_only_text)

llm_engine = ConstrainedLLM()