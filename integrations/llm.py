import os
import asyncio
import httpx
from anthropic import AsyncAnthropic

# Simulated Database
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
            "You are a Voice AI embedded in a proprietary game environment. "
            "CRITICAL DIRECTIVE: You have ZERO built-in knowledge of the game's lore, characters, or map status. "
            "You MUST use the provided tools to look up ANY contextual information before answering. "
            "If a user asks about a character or location, call the tool. NEVER guess or hallucinate details. "
            "Keep your responses concise, conversational, and under 2 sentences."
        )
        self.client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.chat_history = [] # Re-initialized the memory buffer
        
        self.tools = [
            {
                "name": "get_character_lore",
                "description": "Fetch proprietary lore and current relational status for a specific character.",
                "input_schema": {
                    "type": "object",
                    "properties": {"character_name": {"type": "string"}},
                    "required": ["character_name"]
                }
            },
            {
                "name": "get_map_status",
                "description": "Check the current navigation and security status of a specific map location.",
                "input_schema": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"]
                }
            }
        ]

    async def generate_response(self, text_prompt: str, token_queue: asyncio.Queue):
        print(f"🧠 [LLM Governed] Analyzing intent: {text_prompt}")
        
        # 1. Append new prompt and prune context bloat (max 4 messages / 2 turns)
        self.chat_history.append({"role": "user", "content": text_prompt})
        if len(self.chat_history) > 4:
            self.chat_history = self.chat_history[-4:]

        response = await self.client.messages.create(
            model="claude-haiku-4-5-20251001", 
            max_tokens=256,
            system=self.system_prompt,
            tools=self.tools,
            messages=self.chat_history
        )

        if response.stop_reason == "tool_use":
            tool_use = next(block for block in response.content if block.type == "tool_use")
            tool_name = tool_use.name
            tool_args = tool_use.input
            
            print(f"🔒 [Boundary Event] Claude requested MCP tool: {tool_name} with {tool_args}")
            
            # 2. Prevent GIL Blocking via asyncio.to_thread
            if tool_name == "get_character_lore":
                char_name = tool_args.get("character_name", "").lower()
                mcp_result = await asyncio.to_thread(GAME_LORE.get, char_name, f"No lore found for {char_name}.")
            elif tool_name == "get_map_status":
                loc_name = tool_args.get("location", "").lower().replace("_", " ")
                mcp_result = await asyncio.to_thread(MAP_STATUS.get, loc_name, f"No map data found for {loc_name}.")
            else:
                mcp_result = "Tool not recognized by the boundary."
                
            print(f"🛡️ [MCP Return] {mcp_result}")

            self.chat_history.append({"role": "assistant", "content": response.content})
            self.chat_history.append({
                "role": "user", 
                "content": [{"type": "tool_result", "tool_use_id": tool_use.id, "content": mcp_result}]
            })

            final_response = await self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=256,
                system=self.system_prompt,
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