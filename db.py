"""Database abstraction layer - supports PostgreSQL (production) and SQLite (development).

Backend selection is driven entirely by the DATABASE_URL environment variable:
  * DATABASE_URL set  + psycopg importable -> PostgreSQL  (production)
  * otherwise                               -> SQLite       (local development)

All game code talks to this module via get_connection()/get_cursor()/transaction()
and writes SQLite-style "?" placeholders; they are translated to "%s" for
PostgreSQL automatically. Cursors return positional (tuple) rows on BOTH backends
so that row[0]-style access behaves identically.
"""

import os
import re
import sqlite3
from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit, quote

SQLITE_FILE = "game_state.db"


def _encode_userinfo(url):
    """Percent-encode the user:password in a Postgres URL so unescaped special
    characters in the RAW password (notably '@') don't corrupt host parsing.

    A password containing '@' otherwise makes the URI parser split at the wrong
    place, gluing part of the password onto the hostname (e.g. host becomes
    '10@aws-...pooler.supabase.com'). We split on the LAST '@' to recover the
    real host, then re-encode the credentials. No-op for plain passwords.
    DATABASE_URL is expected to carry the raw password; we do the escaping.
    """
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url
    userinfo, hostport = parts.netloc.rsplit("@", 1)
    if ":" in userinfo:
        user, password = userinfo.split(":", 1)
        userinfo = quote(user, safe="") + ":" + quote(password, safe="")
    else:
        userinfo = quote(userinfo, safe="")
    return urlunsplit((parts.scheme, userinfo + "@" + hostport, parts.path, parts.query, parts.fragment))


DB_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = False
_pg = None

if DB_URL:
    try:
        import psycopg as _pg  # psycopg 3 — ships prebuilt wheels, supports modern Python
        USE_POSTGRES = True
        # libpq accepts both schemes, but normalize the legacy form defensively.
        if DB_URL.startswith("postgres://"):
            DB_URL = "postgresql://" + DB_URL[len("postgres://"):]
        # Escape credentials so a special character in the password can't break parsing.
        DB_URL = _encode_userinfo(DB_URL)
    except ImportError:
        print("⚠️ psycopg (v3) not installed, falling back to SQLite")
        USE_POSTGRES = False


def convert_sql(sql):
    """Translate SQLite-style ? placeholders to PostgreSQL %s placeholders."""
    if USE_POSTGRES:
        return re.sub(r"\?", "%s", sql)
    return sql


class _Cursor:
    """Wraps a DB-API cursor so callers can use ? placeholders on either backend.

    Both sqlite3 and psycopg3 default cursors yield tuples, so positional row
    access (row[0]) is uniform; this wrapper only rewrites the placeholder style.
    """

    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=None):
        return self._cur.execute(convert_sql(sql), params if params is not None else ())

    def executemany(self, sql, seq):
        return self._cur.executemany(convert_sql(sql), seq)

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def rowcount(self):
        return self._cur.rowcount

    def close(self):
        return self._cur.close()


def get_connection():
    """Get a database connection (PostgreSQL or SQLite)."""
    if USE_POSTGRES:
        # prepare_threshold=None disables server-side prepared statements, which
        # otherwise break under Supabase's transaction-mode pooler (Supavisor /
        # PgBouncer reuses backends across connections -> "prepared statement
        # already exists"). We open a fresh connection per transaction anyway.
        return _pg.connect(DB_URL, prepare_threshold=None)
    conn = sqlite3.connect(SQLITE_FILE)
    # Wait briefly instead of failing instantly if another connection holds a lock.
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def get_cursor(conn):
    """Get a placeholder-translating cursor that yields tuple rows on both backends."""
    return _Cursor(conn.cursor())


@contextmanager
def transaction():
    """Yield a wrapped cursor inside a transaction.

    Commits on clean exit, rolls back on exception, and always closes the
    connection. Use for every read or write so the active backend stays uniform.
    """
    conn = get_connection()
    cursor = get_cursor(conn)
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def init_tables():
    """Initialize database tables (both SQLite and PostgreSQL)."""
    with transaction() as cursor:
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
                npc_encounters TEXT,
                compromised_locations TEXT,
                FOREIGN KEY (current_location_id) REFERENCES locations(id)
            )
        """)

    # Lightweight migration: add columns introduced after the original schema so
    # a pre-existing database doesn't crash on a missing column. Each ALTER runs
    # in its own transaction and is a harmless no-op if the column already exists.
    for column in ("npc_encounters TEXT", "compromised_locations TEXT"):
        try:
            with transaction() as cursor:
                cursor.execute(f"ALTER TABLE players ADD COLUMN {column}")
            print(f"🔧 Migrated players: added column {column.split()[0]}")
        except Exception:
            pass  # Column already present.

    print(f"✅ Database tables initialized ({'PostgreSQL' if USE_POSTGRES else 'SQLite'})")
