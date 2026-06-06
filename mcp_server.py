import sqlite3
from mcp.server.fastmcp import FastMCP

#Initialize
mcp = FastMCP("LoreBoundaryServer", host="127.0.0.1", port=8001)

DB_FILE = "game_state.db"

def init_db():
    """Initializes the SQLite database with game lore and map status tables."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    #Create tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS locations (
            id TEXT PRIMARY KEY,
            name TEXT,
            is_safe_zone BOOLEAN,
            description TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id TEXT PRIMARY KEY,
            name TEXT,
            health INTEGER,
            status TEXT,
            credits INTEGER,
            current_location_id TEXT,
            inventory TEXT,
            FOREIGN KEY (current_location_id) REFERENCES locations(id)
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM players")
    if cursor.fetchone()[0] == 0:
        print("Seeding initial game state data...")
        cursor.executemany('''
            INSERT INTO locations (id, name, is_safe_zone, description)
            VALUES (?, ?, ?, ?)
        ''', [
            ('loc_001', 'Neon District', False, 'A gritty, neon-lit slum. High gang activity. A good place to lay low, but dangerous to linger.'),
            ('loc_002', 'The Safehouse', True, 'An underground bunker shielded from local scanners. No merchants here, but vitals stabilize.'),
            ('loc_003', 'The Black Market', True, 'A subterranean bazaar. A smuggler here sells the Syndicate Decryption Key for 400 credits.'),
            ('loc_004', 'Syndicate Tower', False, 'A heavily guarded corporate stronghold. Entering here without clearance is essentially a death sentence.'),
            ('loc_005', 'Extraction Rooftop', False, 'The final extraction point. A heavy drop-ship waits in orbit, but requires the Decryption Key to land.')
        ])
        
        cursor.execute('''INSERT INTO players (id, name, health, status, credits, current_location_id, inventory) VALUES (?, ?, ?, ?, ?, ?, ?)''',
                       ('player_1', 'Operative', 100, 'Active', 500, 'loc_001', 'None'))
        conn.commit()
    conn.close()
    print("Database initialized and ready.")
init_db()

@mcp.tool()
def get_player_state(player_id: str) -> str:
    """
    Retrieves the current status, health, credits, and location of a player.
    The AI should call this to check the user's profile and environment.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Join players and locations to get comprehensive status
    cursor.execute('''
        SELECT p.name, p.health, p.status, p.credits, l.name, l.is_safe_zone, p.inventory
        FROM players p
        JOIN locations l ON p.current_location_id = l.id
        WHERE p.id = ?
    ''', (player_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return f"System Error: Player ID '{player_id}' not found in the databanks."
        
    name, health, status, credits, loc_name, is_safe = row
    safe_text = " [SAFE ZONE]" if is_safe else " [COMBAT ZONE]"
    
    # Return a clean, formatted string for Claude to read and interpret
    return (
        f"--- IDENTITY VERIFIED ---\n"
        f"Operative: {name}\n"
        f"Vitals: {health}%\n"
        f"Status: {status}\n"
        f"Balance: {credits} Credits\n"
        f"Inventory: {inventory}\n"
        f"Current Location: {loc_name}{safe_text}"
    )
@mcp.tool()
def grant_item(player_id: str, item_name: str) -> str:
    """
    Adds a specific item to the Operative's inventory.
    Call this ONLY after a successful transaction (like buying the Syndicate Decryption Key) or narrative event.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('SELECT inventory FROM players WHERE id = ?', (player_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return f"System Error: Player ID '{player_id}' not found."

    current_inventory = row[0]
    
    # Append the item cleanly
    if current_inventory == "None" or current_inventory == "":
        new_inventory = item_name
    else:
        new_inventory = f"{current_inventory}, {item_name}"

    cursor.execute('UPDATE players SET inventory = ? WHERE id = ?', (new_inventory, player_id))
    conn.commit()
    conn.close()

    return f"--- INVENTORY UPDATED ---\nItem Acquired: {item_name}"

@mcp.tool()
def transfer_credits(player_id: str, amount: int, recipient_name: str) -> str:
    """
    Transfers Syndicate Credits from the Operative's ledger to external parties.
    Use this to pay off bounties, buy gear in The Black Market, or bribe Syndicate guards.
    Do not use this for arbitrary numbers; only transfer what the Operative explicitly authorizes.
    """
    if amount <= 0:
        return "Transaction Denied: Invalid credit amount."

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 1. Verify current balance
    cursor.execute('SELECT credits FROM players WHERE id = ?', (player_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return f"System Error: Player ID '{player_id}' not found."

    current_balance = row[0]

    # 2. Check for sufficient funds
    if current_balance < amount:
        conn.close()
        return f"Transaction Denied: Insufficient funds. Current balance is {current_balance} credits."

    # 3. Execute the transfer
    new_balance = current_balance - amount
    cursor.execute('UPDATE players SET credits = ? WHERE id = ?', (new_balance, player_id))
    
    conn.commit()
    conn.close()

    return (
        f"--- TRANSACTION APPROVED ---\n"
        f"Transferred: {amount} Credits to {recipient_name}\n"
        f"Remaining Balance: {new_balance} Credits"
    )

@mcp.tool()
def move_location(player_id: str, new_location_name: str) -> str:
    """
    Reroutes the Operative's physical coordinates to a new map hub. 
    Valid destinations include: Neon District, The Safehouse, The Black Market, and Syndicate Tower.
    Call this when the Operative explicitly commands you to navigate, drive, or move them to a new sector.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 1. Verify the destination exists
    cursor.execute('SELECT id, is_safe_zone FROM locations WHERE LOWER(name) = LOWER(?)', (new_location_name,))
    loc_row = cursor.fetchone()

    if not loc_row:
        conn.close()
        return f"Navigation Error: Location '{new_location_name}' does not exist on the map."

    new_loc_id, is_safe = loc_row

    # 2. Verify the player exists and check their current location
    cursor.execute('SELECT current_location_id FROM players WHERE id = ?', (player_id,))
    player_row = cursor.fetchone()

    if not player_row:
        conn.close()
        return f"System Error: Player ID '{player_id}' not found."

    if player_row[0] == new_loc_id:
        conn.close()
        return f"Navigation Error: You are already at {new_location_name}."

    # 3. Execute the move
    cursor.execute('UPDATE players SET current_location_id = ? WHERE id = ?', (new_loc_id, player_id))
    conn.commit()
    conn.close()

    safe_text = " [ENTERING SAFE ZONE]" if is_safe else " [WARNING: COMBAT ZONE]"

    return (
        f"--- NAVIGATION COMPLETE ---\n"
        f"Relocated to: {new_location_name}{safe_text}"
    )

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