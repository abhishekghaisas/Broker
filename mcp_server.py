import random
import json
from db import transaction, init_tables, USE_POSTGRES


# Initial player baseline, reused for seeding and resets.
START_HEALTH = 100
START_CREDITS = 250
START_LOCATION = "loc_002"  # The Safehouse — a secure place to begin the operation


def init_db():
    """Initializes the shared map (SQLite or PostgreSQL).

    Player rows are now per-session (one per WebSocket connection), created on
    connect and removed on disconnect — so we only seed the static `locations`
    table here and clear any player rows left over from a previous run."""
    init_tables()

    with transaction() as cursor:
        cursor.execute("SELECT COUNT(*) FROM locations")
        if cursor.fetchone()[0] == 0:
            print("Seeding map locations...")
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

        # Sessions don't survive a restart; drop stale player rows so the table
        # doesn't accumulate orphans across deploys.
        cursor.execute("DELETE FROM players")

    db_type = 'PostgreSQL' if USE_POSTGRES else 'SQLite'
    print(f"✅ Database initialized successfully ({db_type}).")


def create_session(session_id: str, name: str = "Operative") -> str:
    """Create a fresh player row for a new game session (one per connection).
    Replaces any existing row with the same id (e.g. a reconnect)."""
    with transaction() as cursor:
        cursor.execute("DELETE FROM players WHERE id = ?", (session_id,))
        cursor.execute('''
            INSERT INTO players (id, name, health, status, credits, current_location_id,
                                 inventory, active_puzzle, npc_encounters, compromised_locations)
            VALUES (?, ?, ?, ?, ?, ?, '[]', NULL, '{}', '[]')
        ''', (session_id, name, START_HEALTH, 'Active', START_CREDITS, START_LOCATION))
    return session_id


def delete_session(session_id: str) -> None:
    """Remove a session's player row when its connection closes."""
    with transaction() as cursor:
        cursor.execute("DELETE FROM players WHERE id = ?", (session_id,))


def reset_game(player_id: str, name: str = None) -> str:
    """Resets the session's Operative to the initial state, clearing inventory,
    encounters, compromised locations, and any 'Extracted' status. Used by NOVA's
    in-game reset_game_state tool. The existing callsign is preserved when `name`
    is omitted; passing a name overrides it."""
    with transaction() as cursor:
        if name is None:
            cursor.execute('''
                UPDATE players
                SET health = ?, credits = ?, current_location_id = ?, inventory = '[]',
                    status = 'Active', active_puzzle = NULL, npc_encounters = '{}',
                    compromised_locations = '[]'
                WHERE id = ?
            ''', (START_HEALTH, START_CREDITS, START_LOCATION, player_id))
        else:
            cursor.execute('''
                UPDATE players
                SET name = ?, health = ?, credits = ?, current_location_id = ?, inventory = '[]',
                    status = 'Active', active_puzzle = NULL, npc_encounters = '{}',
                    compromised_locations = '[]'
                WHERE id = ?
            ''', (name, START_HEALTH, START_CREDITS, START_LOCATION, player_id))
    return "Game state has been reset to initial conditions."


def get_player_state(player_id: str = "player_1") -> str:
    """Retrieves the current status, health, credits, location, and inventory of the Operative."""
    with transaction() as cursor:
        cursor.execute('''
            SELECT p.name, p.health, p.credits, p.status, p.inventory, l.name, l.syndicate_presence
            FROM players p
            JOIN locations l ON p.current_location_id = l.id
            WHERE p.id = ?
        ''', (player_id,))
        row = cursor.fetchone()
    if not row:
        return "Error: Player not found."
    return (f"Operative: {row[0]} | Health: {row[1]}% | Credits: {row[2]} | "
            f"Location: {row[5]} (Hostile Presence: {bool(row[6])}) | Inventory: {row[4]}")


def apply_ambient_hazards(player_id: str = "player_1") -> dict:
    """Background game tick. Randomly applies environmental damage in Syndicate-heavy
    zones, escalating in compromised locations where terminals were hacked."""
    with transaction() as cursor:
        cursor.execute('''
            SELECT p.health, p.compromised_locations, l.syndicate_presence, l.name
            FROM players p
            JOIN locations l ON p.current_location_id = l.id
            WHERE p.id = ?
        ''', (player_id,))
        row = cursor.fetchone()
        if not row:
            return {"damage_taken": 0, "status": "Error: Player not found"}

        current_health, compromised_json, syndicate_presence, location_name = row
        compromised = json.loads(compromised_json or "[]")
        is_compromised = location_name in compromised
        damage_taken = 0

        if syndicate_presence:
            if is_compromised:
                # Compromised: 40% chance, higher damage (15-25).
                if random.random() < 0.40:
                    damage_taken = random.randint(15, 25)
            else:
                # Standard: 30% chance, normal damage (5-15).
                if random.random() < 0.30:
                    damage_taken = random.randint(5, 15)

            if damage_taken:
                new_health = max(0, current_health - damage_taken)
                cursor.execute("UPDATE players SET health = ? WHERE id = ?", (new_health, player_id))

    return {"damage_taken": damage_taken, "location": location_name}


def track_npc_aggravation(player_id: str, npc_name: str, is_failed: bool) -> dict:
    """Track NPC aggravation on failed negotiation. Returns consequences if needed."""
    with transaction() as cursor:
        cursor.execute("SELECT npc_encounters FROM players WHERE id = ?", (player_id,))
        row = cursor.fetchone()
        encounters = json.loads(row[0] or "{}") if row else {}

        if is_failed:
            encounters[npc_name] = encounters.get(npc_name, 0) + 1
            aggravation = encounters[npc_name]
            cursor.execute("UPDATE players SET npc_encounters = ? WHERE id = ?",
                           (json.dumps(encounters), player_id))

            if aggravation == 1:
                return {"level": "annoyed", "damage": 0, "message": f"{npc_name} is annoyed. Don't push further."}
            elif aggravation == 2:
                return {"level": "aggravated", "damage": 10, "message": f"{npc_name} is aggravated! Takes 10-15 damage."}
            else:
                return {"level": "hostile", "damage": 20, "message": f"{npc_name} is hostile! Takes 20-30 damage."}
        else:
            # Success: reset this NPC's aggravation.
            encounters.pop(npc_name, None)
            cursor.execute("UPDATE players SET npc_encounters = ? WHERE id = ?",
                           (json.dumps(encounters), player_id))
            return {"level": "friendly", "damage": 0, "message": f"{npc_name} is satisfied."}


def end_game(player_id: str = "player_1") -> str:
    """Ends the game session and provides a final summary of the player's journey."""
    with transaction() as cursor:
        cursor.execute('''
            SELECT p.name, p.health, p.credits, p.status, p.inventory, l.name
            FROM players p
            JOIN locations l ON p.current_location_id = l.id
            WHERE p.id = ?
        ''', (player_id,))
        row = cursor.fetchone()
    if not row:
        return "Error: Player not found."
    return (f"Final Summary for {row[0]}:\nHealth: {row[1]}%\nCredits: {row[2]}\n"
            f"Status: {row[3]}\nLocation: {row[5]}\nInventory: {row[4]}")
