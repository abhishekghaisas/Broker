from mcp.server.fastmcp import FastMCP

#Initialize
mcp = FastMCP("LoreBoundaryServer", host="127.0.0.1", port=8001)

#Simulated Game State/Lore

GAME_LORE = {
    "alan": "Alan is a rogue synth who operates in the Neon District. He currently owes a great debt to the Syndicate.",
    "syndicate": "A ruthless corporate crime organization that controls the black market weapon trade."
}

MAP_STATUS = {
    "neon district": "Currently under lockdown due to a recent Syndicate raid. Hostile entities present.",
    "safehouse": "Clear and available for secure navigation."
}

#Governed tools
@mcp.tool()
def get_character_lore(character_name: str) -> str:
    """Fetch proprietary lore and current relational status for a specific character."""
    print(f"[MCP Boundary] LLM requested lore for: {character_name}")
    return GAME_LORE.get(character_name.lower(), "Character not found in game lore database")

@mcp.tool()
def get_map_status(location: str) -> str:
    """Check the current navigation and security status of a specific map location."""
    print(f"[MCP Boundary] LLM requested map status for: {location}")
    return MAP_STATUS.get(location.lower(), "Location not found or currently inaccesible.")

if __name__ == "__main__":
    print("Zero-Knowledge MCP Server Booting Up....")
    print("Listening for tool calls on http://localhost:8001/sse")
    #Run the server over Server-Sent Events(SSE) for local microservice communication
    mcp.run(transport='sse')