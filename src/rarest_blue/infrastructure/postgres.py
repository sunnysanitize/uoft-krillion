"""Postgres adapter: the repositories and the unit of work.

Works against plain Postgres and Supabase's transaction pooler alike. The tables must match
supabase/migrations/*_rarest_blue_init.sql, which also locks them away from Supabase's public APIs.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from ..application.ports import PromptStats
from ..domain.models import Prompt, ScoredGuess

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


# prepare_threshold=None: Supabase's transaction pooler can't hold prepared statements.
CONNECT_ARGS = {"row_factory": dict_row, "prepare_threshold": None}


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url, **CONNECT_ARGS)


def open_pool(url: str, min_size: int = 1, max_size: int = 10) -> ConnectionPool:
    """A small pool of warm connections, so a request doesn't pay for a fresh TLS + auth handshake.

    Each connection is checked before it's handed out, since Supabase's pooler closes idle ones; idle connections
    are retired after 5 minutes. max_size x Cloud Run's max instances stays well under the pooler's client limit.
    """
    pool = ConnectionPool(
        url,
        min_size=min_size,
        max_size=max_size,
        kwargs=CONNECT_ARGS,
        check=ConnectionPool.check_connection,
        max_idle=300,
        timeout=10,
        open=False,
        name="rarest-blue",
    )
    pool.open(wait=True, timeout=30)
    return pool


def init_schema(url: str) -> None:
    with connect(url) as conn:
        conn.execute(SCHEMA)


def _key(day: date) -> str:
    return day.isoformat()


class PostgresPromptRepository:
    def __init__(self, conn: psycopg.Connection):
        self._conn = conn

    def get(self, day: date) -> list[Prompt] | None:
        row = self._conn.execute("SELECT prompts FROM daily_prompts WHERE day = %s", (_key(day),)).fetchone()
        return [Prompt.from_dict(p) for p in row["prompts"]] if row else None

    def add(self, day: date, prompts: list[Prompt], source: str) -> bool:
        cur = self._conn.execute(
            "INSERT INTO daily_prompts (day, prompts, source) VALUES (%s, %s, %s) ON CONFLICT (day) DO NOTHING",
            (_key(day), Jsonb([p.to_dict() for p in prompts]), source),
        )
        return cur.rowcount == 1

    def replace_prompt(self, day: date, prompt: Prompt) -> None:
        prompts = [prompt if p.id == prompt.id else p for p in self.get(day) or []]
        self._conn.execute(
            "UPDATE daily_prompts SET prompts = %s WHERE day = %s", (Jsonb([p.to_dict() for p in prompts]), _key(day))
        )

    def recent(self, before: date, days: int) -> list[Prompt]:
        rows = self._conn.execute(
            "SELECT prompts FROM daily_prompts WHERE day < %s ORDER BY day DESC LIMIT %s", (_key(before), days)
        )
        return [Prompt.from_dict(p) for row in rows for p in row["prompts"]]


class PostgresGuessRepository:
    def __init__(self, conn: psycopg.Connection):
        self._conn = conn

    def find(self, day: date, prompt_id: str, player_id: str) -> ScoredGuess | None:
        row = self._conn.execute(
            "SELECT answer, points, share FROM guesses WHERE day = %s AND prompt_id = %s AND player_id = %s",
            (_key(day), prompt_id, player_id),
        ).fetchone()
        return ScoredGuess(answer=row["answer"], points=row["points"], share=row["share"]) if row else None

    def add(self, day: date, prompt_id: str, player_id: str, raw: str, guess: ScoredGuess) -> bool:
        cur = self._conn.execute(
            "INSERT INTO guesses (day, prompt_id, player_id, raw, answer, points, share) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (_key(day), prompt_id, player_id, raw, guess.answer, guess.points, guess.share),
        )
        return cur.rowcount == 1

    def stats(self, day: date, prompt_id: str | None = None) -> dict[str, PromptStats]:
        sql = "SELECT prompt_id, answer, COUNT(*) AS n FROM guesses WHERE day = %s"
        params: tuple = (_key(day),)
        if prompt_id is not None:
            sql += " AND prompt_id = %s"
            params += (prompt_id,)
        tallies: dict[str, dict[str, int]] = {}
        players: dict[str, int] = {}
        for row in self._conn.execute(sql + " GROUP BY prompt_id, answer", params):
            pid = row["prompt_id"]
            players[pid] = players.get(pid, 0) + row["n"]
            if row["answer"] is not None:
                tallies.setdefault(pid, {})[row["answer"]] = row["n"]
        return {pid: PromptStats(tallies.get(pid, {}), n) for pid, n in players.items()}

    def tallies(self, day: date, prompt_id: str) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT answer, COUNT(*) AS n FROM guesses WHERE day = %s AND prompt_id = %s AND answer IS NOT NULL "
            "GROUP BY answer",
            (_key(day), prompt_id),
        )
        return {row["answer"]: row["n"] for row in rows}

    def player_count(self, day: date, prompt_id: str) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) AS n FROM guesses WHERE day = %s AND prompt_id = %s", (_key(day), prompt_id)
        ).fetchone()["n"]

    def player_total(self, day: date, player_id: str) -> int:
        return self._conn.execute(
            "SELECT COALESCE(SUM(points), 0)::int AS total FROM guesses WHERE day = %s AND player_id = %s",
            (_key(day), player_id),
        ).fetchone()["total"]

    def rejected(self, day: date) -> list[tuple[str, str]]:
        rows = self._conn.execute(
            "SELECT prompt_id, raw FROM guesses WHERE day = %s AND answer IS NULL", (_key(day),)
        ).fetchall()
        return [(r["prompt_id"], r["raw"]) for r in rows]

    def unmatched(self, day: date, prompt_id: str) -> list[tuple[str, str]]:
        rows = self._conn.execute(
            "SELECT player_id, raw FROM guesses WHERE day = %s AND prompt_id = %s AND answer IS NULL",
            (_key(day), prompt_id),
        ).fetchall()
        return [(r["player_id"], r["raw"]) for r in rows]

    def set_answer(self, day: date, prompt_id: str, player_id: str, answer: str) -> None:
        self._conn.execute(
            "UPDATE guesses SET answer = %s WHERE day = %s AND prompt_id = %s AND player_id = %s",
            (answer, _key(day), prompt_id, player_id),
        )

    def set_score(self, day: date, prompt_id: str, player_id: str, points: int, share: float) -> None:
        self._conn.execute(
            "UPDATE guesses SET points = %s, share = %s WHERE day = %s AND prompt_id = %s AND player_id = %s",
            (points, share, _key(day), prompt_id, player_id),
        )

    def delete_player(self, day: date, player_id: str) -> None:
        self._conn.execute("DELETE FROM guesses WHERE day = %s AND player_id = %s", (_key(day), player_id))


class PostgresFinishRepository:
    def __init__(self, conn: psycopg.Connection):
        self._conn = conn

    def upsert(self, day: date, player_id: str, nickname: str, score: int) -> None:
        self._conn.execute(
            "INSERT INTO finishes (day, player_id, nickname, score) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (day, player_id) DO UPDATE SET nickname = EXCLUDED.nickname, score = EXCLUDED.score",
            (_key(day), player_id, nickname, score),
        )

    def count_below(self, day: date, score: int) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) AS n FROM finishes WHERE day = %s AND score < %s", (_key(day), score)
        ).fetchone()["n"]

    def count(self, day: date) -> int:
        return self._conn.execute("SELECT COUNT(*) AS n FROM finishes WHERE day = %s", (_key(day),)).fetchone()["n"]

    def top(self, day: date, limit: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT nickname, score FROM finishes WHERE day = %s ORDER BY score DESC LIMIT %s",
            (_key(day), limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def recompute_scores(self, day: date, player_ids: list[str]) -> None:
        self._conn.execute(
            "UPDATE finishes f SET score = (SELECT COALESCE(SUM(points), 0) FROM guesses g "
            "WHERE g.day = f.day AND g.player_id = f.player_id) WHERE day = %s AND player_id = ANY(%s)",
            (_key(day), player_ids),
        )

    def delete_player(self, day: date, player_id: str) -> None:
        self._conn.execute("DELETE FROM finishes WHERE day = %s AND player_id = %s", (_key(day), player_id))


class PostgresUnitOfWork:
    """One connection, one transaction. Commits on a clean exit, rolls back on an exception.

    With a pool, the connection is borrowed and returned; without one (CLI jobs), it's opened and closed.
    """

    def __init__(self, url: str | None = None, pool: ConnectionPool | None = None):
        if (url is None) == (pool is None):
            raise ValueError("give exactly one of url or pool")
        self._url = url
        self._pool = pool
        self._conn: psycopg.Connection | None = None

    def __enter__(self) -> PostgresUnitOfWork:
        self._conn = self._pool.getconn() if self._pool else connect(self._url)
        self.prompts = PostgresPromptRepository(self._conn)
        self.guesses = PostgresGuessRepository(self._conn)
        self.finishes = PostgresFinishRepository(self._conn)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self._conn is not None
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            if self._pool:
                self._pool.putconn(self._conn)
            else:
                self._conn.close()
            self._conn = None
