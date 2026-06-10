import asyncio
import sqlite3
import random
from mcp.server.fastmcp import FastMCP

#Initialize FastMCP Server
mcp = FastMCP("LoreBoundaryServer", host="0.0.0.0", port=8001)

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
            description TEXT,
            syndicate_presence BOOLEAN
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
            active_puzzle TEXT,
            FOREIGN KEY (current_location_id) REFERENCES locations(id)
        )
    """)

    #Seed Data if empty
    cursor.execute("SELECT COUNT(*) FROM players")
    if cursor.fetchone()[0] == 0:
        print("Seeding initial game state data...")
        #Locations
        cursor.executemany('''
            INSERT INTO locations (id, name, is_safe_zone, description, syndicate_presence)
            VALUES (?, ?, ?, ?, ?)
        ''', [
            ('loc_001', 'Neon District', False, 'A gritty, neon-lit slum. High gang activity. A good place to lay low, but dangerous to linger.', False),
            ('loc_002', 'The Safehouse', True, 'A secure, encrypted bunker. No hostile entities can track you here.', False),
            ('loc_003', 'Syndicate Tower', False, 'Heavily guarded corporate stronghold. High risk, high reward.', True),
            ('loc_004', 'The Black Market', True, 'An underground bazaar for smugglers and fixers.', False),
            ('loc_005', 'The Extraction Rooftop', True, 'A hidden rooftop with a helicopter pad. The only way off the map.', False)
        ])
        
        #Player (Starts with 250 credits to balance the 400 credit goal)
        cursor.execute('''
            INSERT INTO players (id, name, health, status, credits, current_location_id, inventory, active_puzzle)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', ('player_1', 'Operative', 100, 'Active', 250, 'loc_001', '[]', None))

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

async def run_db_op(func, *args):
    return await asyncio.to_thread(func, *args)

#Background Physics Engine to apply random damage in hostile zones

def apply_ambient_hazards(player_id: str = "player_1") -> dict:
    """
    Acts as a background game tick. Checks the player's location and 
    randomly applies damage if they are in a Syndicate-heavy zone.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT p.health, l.syndicate_presence, l.name 
        FROM players p
        JOIN locations l ON p.current_location_id = l.id
        WHERE p.id = ?
    ''', (player_id,))
    
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"damage_taken": 0, "status": "Error: Player not found"}
        
    current_health, syndicate_presence, location_name = row
    damage_taken = 0
    
    #The Math Formula: 30% chance to take 5 to 15 damage in hostile zones
    if syndicate_presence:
        if random.random() < 0.30: # 30% probability
            damage_taken = random.randint(5, 15)
            new_health = max(0, current_health - damage_taken)
            
            cursor.execute("UPDATE players SET health = ? WHERE id = ?", (new_health, player_id))
            conn.commit()
            
    conn.close()
    return {"damage_taken": damage_taken, "location": location_name}


#FastMCP Tools

@mcp.tool()
def get_player_state(player_id: str) -> str:
    """Retrieves the current status, health, credits, and location of the Operative."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.name, p.health, p.credits, p.status, p.inventory, l.name, l.syndicate_presence
        FROM players p
        JOIN locations l ON p.current_location_id = l.id
        WHERE p.id = ?
    ''', (player_id,))
    row = cursor.fetchone()
    conn.close()
    if not row: return "Error: Player not found."
    return f"Operative: {row[0]} | Health: {row[1]}% | Credits: {row[2]} | Location: {row[5]} (Hostile Presence: {bool(row[6])}) | Inventory: {row[4]}"

@mcp.tool()
def move_location(player_id: str, new_location_name: str) -> str:
    """Reroutes the Operative's physical coordinates."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM locations WHERE name = ?", (new_location_name,))
    loc = cursor.fetchone()
    if not loc:
        conn.close()
        return "Error: Location unknown."
    cursor.execute("UPDATE players SET current_location_id = ? WHERE id = ?", (loc[0], player_id))
    conn.commit()
    conn.close()
    return f"Relocation successful. Operative is now at {new_location_name}."

@mcp.tool()
def transfer_credits(player_id: str, amount: int, recipient_name: str) -> str:
    """Transfers Syndicate Credits from the Operative's ledger to external parties."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT credits FROM players WHERE id = ?", (player_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "Error: Player not found."
    if row[0] < amount:
        conn.close()
        return f"Transaction failed: Insufficient funds. Current balance: {row[0]}."
    new_balance = row[0] - amount
    cursor.execute("UPDATE players SET credits = ? WHERE id = ?", (new_balance, player_id))
    conn.commit()
    conn.close()
    return f"Transferred {amount} to {recipient_name}. Remaining balance: {new_balance} credits."

@mcp.tool()
def adjust_credits(player_id: str, amount: int) -> str:
    """Adjusts the player's credit balance. Positive for rewards, negative for penalties."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT credits FROM players WHERE id = ?", (player_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "Error: Player not found."
    new_balance = max(0, row[0] + amount)
    cursor.execute("UPDATE players SET credits = ? WHERE id = ?", (new_balance, player_id))
    conn.commit()
    conn.close()
    return f"Transaction Complete. New balance: {new_balance} Credits"

@mcp.tool()
def adjust_health(player_id: str, amount: int) -> str:
    """Adjusts player health. Negative for damage, positive for heal."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT health FROM players WHERE id = ?", (player_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "Error: Player not found."
    new_health = max(0, min(100, row[0] + amount))
    cursor.execute("UPDATE players SET health = ? WHERE id = ?", (new_health, player_id))
    conn.commit()
    conn.close()
    if new_health == 0: return "CRITICAL: Player health has reached 0. Operative is deceased."
    return f"Vitals updated. Current health: {new_health}%."

@mcp.tool()
def grant_item(player_id: str, item_name: str) -> str:
    """Adds a specific item to the Operative's inventory."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT inventory FROM players WHERE id = ?", (player_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "Error: Player not found."
    import json
    inv = json.loads(row[0])
    if item_name not in inv:
        inv.append(item_name)
    cursor.execute("UPDATE players SET inventory = ? WHERE id = ?", (json.dumps(inv), player_id))
    conn.commit()
    conn.close()
    return f"Item '{item_name}' added to inventory."

@mcp.tool()
def reset_game_state() -> str:
    """Resets the Operative's status, inventory, credits, and location to the initial default state."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE players 
        SET health = 100, credits = 250, current_location_id = 'loc_001', inventory = '[]' 
        WHERE id = 'player_1'
    ''')
    conn.commit()
    conn.close()
    return "Game state has been reset to initial conditions."
@mcp.tool()
def end_game() -> str:
    """Ends the game session and provides a final summary of the player's journey."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.name, p.health, p.credits, p.status, p.inventory, l.name 
        FROM players p
        JOIN locations l ON p.current_location_id = l.id
        WHERE p.id = 'player_1'
    ''')
    row = cursor.fetchone()
    conn.close()
    if not row: return "Error: Player not found."
    summary = f"Final Summary for {row[0]}:\nHealth: {row[1]}%\nCredits: {row[2]}\nStatus: {row[3]}\nLocation: {row[5]}\nInventory: {row[4]}"
    return summary

if __name__ == "__main__":
    init_db()
    print("Zero-Knowledge MCP Server Booting Up....")
    mcp.run()