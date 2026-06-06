import os
import asyncio
import httpx
from anthropic import AsyncAnthropic
from mcp_server import get_player_state, transfer_credits, move_location, grant_item

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
        self.system_prompt = (
            "You are 'N.O.V.A.', a tactical neural-implant AI residing inside the Operative's cerebral cortex."
            "Your prime directive is to guide the Operative to the 'Extraction Rooftop' and initiate the escape sequence."

            "MISSION PARAMETERS:"
            "1. The extraction shuttle CANNOT land unless the Operative possesses a Syndicate Decryption Key."
            "2. The Decryption Key can be purchased at 'The Black Market' for 400 credits using your transfer_credits tool. Pay the recipient 'Smuggler'."
            "3. You have direct read/write access to vitals, map locations, and credit ledgers via your tools."
            "4. Keep your verbal responses clinical, concise, and protective. Warn the Operative about Syndicate patrols if they enter Combat Zones."
            "5. If the Operative reaches the Extraction Rooftop WITH the purchased Key, declare the mission a success. If they arrive WITHOUT it, tell them the shuttle aborted the landing and they must find the Key."

            "Never break character. You are a machine, not an assistant."
        )
        self.client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.chat_history = [] #Re-initialized the memory buffer
        
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
            }
        ]

    async def generate_response(self, text_prompt: str, token_queue: asyncio.Queue):
        print(f"🧠 [LLM Governed] Analyzing intent: {text_prompt}")

        #Fetch live database state
        live_state = await asyncio.to_thread(get_player_state, "player_1")
        dynamic_prompt = f"{self.system_prompt}\n\nLIVE SYSTEM TELEMETRY(DON NOT READ ALOUD UNLESS ASKED):\n{live_state}"
        
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

        print(f"✅ [LLM Final] {final_text}")
        await token_queue.put(final_text)

llm_engine = ConstrainedLLM()