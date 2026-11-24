"""SQLite storage for guesses and the daily leaderboard."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("RAREST_BLUE_DB", Path(__file__).resolve().parent.parent / "rarest_blue.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS guesses (
    day TEXT NOT NULL,
    prompt_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    raw TEXT NOT NULL,
    answer TEXT,
    points INTEGER NOT NULL,
    share REAL NOT NULL,
    PRIMARY KEY (day, prompt_id, player_id)
);
CREATE TABLE IF NOT EXISTS finishes (
    day TEXT NOT NULL,
    player_id TEXT NOT NULL,
    nickname TEXT NOT NULL,
    college TEXT,
    score INTEGER NOT NULL,
    PRIMARY KEY (day, player_id)
);
"""


@contextmanager
def connect(path: Path | None = None):
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()
