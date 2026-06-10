"""Database abstraction layer - supports PostgreSQL (production) and SQLite (development)."""

import os
import re
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = DB_URL is not None

def convert_sql(sql):
    """Convert SQLite SQL (with ?) to PostgreSQL SQL (with %s)."""
    if USE_POSTGRES:
        # Replace ? with %s for PostgreSQL
        return re.sub(r'\?', '%s', sql)
    return sql

def get_connection():
    """Get database connection (PostgreSQL or SQLite)."""
    if USE_POSTGRES:
        conn = psycopg2.connect(DB_URL)
        return conn
    else:
        return sqlite3.connect("game_state.db")

def get_cursor(conn):
    """Get cursor from connection."""
    if USE_POSTGRES:
        return conn.cursor(cursor_factory=RealDictCursor)
    else:
        conn.row_factory = sqlite3.Row
        return conn.cursor()

def execute_query(query, params=None):
    """Execute a query and return results (helper for both databases)."""
    conn = get_connection()
    cursor = get_cursor(conn)

    try:
        query = convert_sql(query)
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        result = cursor.fetchall()
        conn.commit()
        return result
    finally:
        cursor.close()
        conn.close()

def execute_update(query, params=None):
    """Execute an update/insert/delete query."""
    conn = get_connection()
    cursor = get_cursor(conn)

    try:
        query = convert_sql(query)
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()

def init_tables():
    """Initialize database tables (both SQLite and PostgreSQL)."""
    conn = get_connection()
    cursor = get_cursor(conn)

    try:
        # Create tables (SQL works for both databases)
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

        conn.commit()
        print(f"✅ Database initialized ({'PostgreSQL' if USE_POSTGRES else 'SQLite'})")
    finally:
        cursor.close()
        conn.close()
