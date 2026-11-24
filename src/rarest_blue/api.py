"""FastAPI app: run with `uvicorn rarest_blue.api:app --reload` from src/."""

import os
import random
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import db, game
from .prompts import Prompt

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_schema()
    yield


app = FastAPI(title="UofT Krillion", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class CheckIn(BaseModel):
    prompt_id: str
    answer: str = Field(max_length=80)


class GuessIn(BaseModel):
    player_id: str = Field(min_length=8, max_length=64)
    prompt_id: str
    answer: str = Field(max_length=80)


class PlayerIn(BaseModel):
    player_id: str = Field(min_length=8, max_length=64)


class PlayerPromptIn(BaseModel):
    player_id: str = Field(min_length=8, max_length=64)
    prompt_id: str


class FinishIn(BaseModel):
    player_id: str = Field(min_length=8, max_length=64)
    nickname: str = Field(min_length=1, max_length=20)


def _prompts_for(conn, day: date) -> list[Prompt]:
    """The day's set: whatever the nightly job stored, else the built-in fallback.

    The fallback is stored on first use so the day's set can't change mid-day.
    """
    prompts = db.load_prompts(conn, day)
    if prompts is None:
        db.save_prompts(conn, day, game.fallback_prompts(day), source="fallback")
        prompts = db.load_prompts(conn, day)
    return prompts


def _reveal(counts: dict[str, int], players: int) -> dict:
    total = sum(counts.values())
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    top = [{"answer": a, "pct": round(100 * n / total, 1)} for a, n in ranked[:6]]
    # Surface a few deep cuts so players learn something for tomorrow.
    deep_cuts = [a for a, _ in ranked[len(ranked) // 2 :]]
    random.shuffle(deep_cuts)
    return {"top": top, "deep_cuts": deep_cuts[:3], "players": players, "valid_answers": len(counts)}


@app.get("/api/daily")
def daily():
    day = game.today()
    with db.connect() as conn:
        prompts = _prompts_for(conn, day)
    return {
        "day": day.isoformat(),
        "number": game.puzzle_number(day),
        "time_limit": game.TIME_LIMIT_SECONDS,
        "meters_per_point": game.METERS_PER_POINT,
        "zones": [{"start": start, "name": name} for start, name in game.ZONES],
        "prompts": [{"id": p.id, "text": p.text, "hint": p.hint} for p in prompts],
    }


@app.post("/api/check")
def check(body: CheckIn):
    """Before a guess counts: is it recognized, and is it right? Only right answers spend the prompt;
    wrong ones get another try until the clock runs out."""
    with db.connect() as conn:
        prompt = next((p for p in _prompts_for(conn, game.today()) if p.id == body.prompt_id), None)
    if prompt is None:
        raise HTTPException(400, "That prompt isn't in today's set.")
    recognized, suggestion = game.recognize(prompt, body.answer)
    correct = recognized and game.match_answer(prompt, body.answer) is not None
    return {"recognized": recognized, "correct": correct, "suggestion": suggestion}


@app.post("/api/guess")
def guess(body: GuessIn):
    day = game.today()
    key = day.isoformat()

    with db.connect() as conn:
        prompt = next((p for p in _prompts_for(conn, day) if p.id == body.prompt_id), None)
        if prompt is None:
            raise HTTPException(400, "That prompt isn't in today's set.")
        existing = conn.execute(
            "SELECT answer, points, share FROM guesses WHERE day = %s AND prompt_id = %s AND player_id = %s",
            (key, body.prompt_id, body.player_id),
        ).fetchone()
        if existing:
            answer, points, share = existing["answer"], existing["points"], existing["share"]
        else:
            answer = game.match_answer(prompt, body.answer)
            counts = db.answer_counts(conn, key, prompt)
            share = counts.get(answer, 0) / sum(counts.values()) if answer else 1.0
            points = game.score(share, answer == prompt.golden) if answer else 0
            conn.execute(
                "INSERT INTO guesses (day, prompt_id, player_id, raw, answer, points, share) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (key, body.prompt_id, body.player_id, body.answer, answer, points, share),
            )
        players = conn.execute(
            "SELECT COUNT(*) AS n FROM guesses WHERE day = %s AND prompt_id = %s", (key, body.prompt_id)
        ).fetchone()["n"]
        reveal = _reveal(db.answer_counts(conn, key, prompt), players)

    return {
        "valid": answer is not None,
        "answer": answer,
        "points": points,
        "share_pct": round(100 * share, 1) if answer else None,
        "rarity": game.rarity_label(share, answer == prompt.golden) if answer else None,
        "golden": answer is not None and answer == prompt.golden,
        "golden_answer": prompt.golden,
        **reveal,
    }


@app.post("/api/answers")
def answers(body: PlayerPromptIn):
    """Every valid answer to a prompt with its share and points right now, rarest first.

    Only for a player who has already answered (or run out of air on) that prompt today.
    """
    key = game.today().isoformat()
    with db.connect() as conn:
        prompt = next((p for p in _prompts_for(conn, game.today()) if p.id == body.prompt_id), None)
        if prompt is None:
            raise HTTPException(400, "That prompt isn't in today's set.")
        played = conn.execute(
            "SELECT answer FROM guesses WHERE day = %s AND prompt_id = %s AND player_id = %s",
            (key, body.prompt_id, body.player_id),
        ).fetchone()
        if played is None:
            raise HTTPException(403, "Answer this prompt first.")
        counts = db.answer_counts(conn, key, prompt)
    total = sum(counts.values())
    rows = []
    for names in prompt.answers:
        name = names[0]
        share = counts.get(name, 0) / total
        golden = name == prompt.golden
        rows.append({
            "answer": name,
            "pct": round(100 * share, 1),
            "points": game.score(share, golden),
            "rarity": game.rarity_label(share, golden),
            "golden": golden,
            "yours": name == played["answer"],
        })
    rows.sort(key=lambda r: (-r["points"], r["pct"], r["answer"]))
    return {"answers": rows}


@app.post("/api/finish")
def finish(body: FinishIn):
    key = game.today().isoformat()
    with db.connect() as conn:
        total = conn.execute(
            "SELECT COALESCE(SUM(points), 0)::int AS total FROM guesses WHERE day = %s AND player_id = %s",
            (key, body.player_id),
        ).fetchone()["total"]
        conn.execute(
            "INSERT INTO finishes (day, player_id, nickname, score) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (day, player_id) DO UPDATE SET nickname = EXCLUDED.nickname, score = EXCLUDED.score",
            (key, body.player_id, body.nickname.strip(), total),
        )
        beaten = conn.execute(
            "SELECT COUNT(*) AS n FROM finishes WHERE day = %s AND score < %s", (key, total)
        ).fetchone()["n"]
        field = conn.execute("SELECT COUNT(*) AS n FROM finishes WHERE day = %s", (key,)).fetchone()["n"]
    percentile = round(100 * beaten / (field - 1)) if field > 1 else 100
    return {"score": total, "percentile": percentile, "players": field}


@app.get("/api/leaderboard")
def leaderboard():
    key = game.today().isoformat()
    with db.connect() as conn:
        players = conn.execute(
            "SELECT nickname, score FROM finishes WHERE day = %s ORDER BY score DESC LIMIT 15", (key,)
        ).fetchall()
    return {"players": [dict(r) for r in players]}


# Local testing only: lets a player replay today. Never set DEV_RESET in production.
if os.environ.get("DEV_RESET") == "1":

    @app.post("/api/dev/reset")
    def dev_reset(body: PlayerIn):
        key = game.today().isoformat()
        with db.connect() as conn:
            for table in ("guesses", "finishes"):
                conn.execute(f"DELETE FROM {table} WHERE day = %s AND player_id = %s", (key, body.player_id))
        return {"ok": True}
