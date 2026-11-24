"""Postgres storage for the daily prompt sets, guesses, and the daily leaderboard."""

import os
from contextlib import contextmanager
from datetime import date

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from . import game
from .prompts import Prompt, from_dict, to_dict

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_prompts (
    day TEXT PRIMARY KEY,
    prompts JSONB NOT NULL,
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS guesses (
    day TEXT NOT NULL,
    prompt_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    raw TEXT NOT NULL,
    answer TEXT,
    points INTEGER NOT NULL,
    share DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (day, prompt_id, player_id)
);
CREATE TABLE IF NOT EXISTS finishes (
    day TEXT NOT NULL,
    player_id TEXT NOT NULL,
    nickname TEXT NOT NULL,
    score INTEGER NOT NULL,
    PRIMARY KEY (day, player_id)
);
-- Players used to represent a college; scores are individual now.
ALTER TABLE finishes DROP COLUMN IF EXISTS college;
"""


@contextmanager
def connect(url: str | None = None):
    # prepare_threshold=None: Supabase's transaction pooler can't hold prepared statements.
    with psycopg.connect(url or DATABASE_URL, row_factory=dict_row, prepare_threshold=None) as conn:
        yield conn


def init_schema() -> None:
    with connect() as conn:
        conn.execute(SCHEMA)


def load_prompts(conn, day: date) -> list[Prompt] | None:
    row = conn.execute("SELECT prompts FROM daily_prompts WHERE day = %s", (day.isoformat(),)).fetchone()
    return [from_dict(p) for p in row["prompts"]] if row else None


def save_prompts(conn, day: date, prompts: list[Prompt], source: str) -> bool:
    """Store a day's set. Returns False if that day already has one (first write wins)."""
    cur = conn.execute(
        "INSERT INTO daily_prompts (day, prompts, source) VALUES (%s, %s, %s) ON CONFLICT (day) DO NOTHING",
        (day.isoformat(), Jsonb([to_dict(p) for p in prompts]), source),
    )
    return cur.rowcount == 1


def replace_prompt(conn, day: date, prompt: Prompt) -> None:
    """Swap one prompt in a stored set, e.g. to accept an answer the list missed."""
    prompts = [prompt if p.id == prompt.id else p for p in load_prompts(conn, day)]
    conn.execute(
        "UPDATE daily_prompts SET prompts = %s WHERE day = %s",
        (Jsonb([to_dict(p) for p in prompts]), day.isoformat()),
    )


def answer_counts(conn, day: str, prompt: Prompt) -> dict[str, int]:
    """How often each answer has been given today, on top of the list-order priors."""
    counts = game.prior_counts(prompt)
    rows = conn.execute(
        "SELECT answer, COUNT(*) AS n FROM guesses WHERE day = %s AND prompt_id = %s AND answer IS NOT NULL GROUP BY answer",
        (day, prompt.id),
    )
    for row in rows:
        counts[row["answer"]] = counts.get(row["answer"], 0) + row["n"]
    return counts


def recent_prompt_texts(conn, before: date, days: int) -> list[str]:
    rows = conn.execute(
        "SELECT prompts FROM daily_prompts WHERE day < %s ORDER BY day DESC LIMIT %s", (before.isoformat(), days)
    )
    return [p["text"] for row in rows for p in row["prompts"]]
