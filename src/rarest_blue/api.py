"""FastAPI app: run with `uvicorn rarest_blue.api:app --reload` from src/."""

import os
import random

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import db, game
from .prompts import PROMPTS_BY_ID

COLLEGES = ["Trinity", "Victoria", "UC", "St. Mike's", "Innis", "New", "Woodsworth", "UTM", "UTSC", "Grad / Other"]

app = FastAPI(title="Rarest Blue")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class GuessIn(BaseModel):
    player_id: str = Field(min_length=8, max_length=64)
    prompt_id: str
    answer: str = Field(max_length=80)


class FinishIn(BaseModel):
    player_id: str = Field(min_length=8, max_length=64)
    nickname: str = Field(min_length=1, max_length=20)
    college: str | None = None


def _counts(conn, day: str, prompt_id: str) -> dict[str, int]:
    prompt = PROMPTS_BY_ID[prompt_id]
    counts = game.prior_counts(prompt)
    rows = conn.execute(
        "SELECT answer, COUNT(*) AS n FROM guesses WHERE day = ? AND prompt_id = ? AND answer IS NOT NULL GROUP BY answer",
        (day, prompt_id),
    )
    for row in rows:
        counts[row["answer"]] = counts.get(row["answer"], 0) + row["n"]
    return counts


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
    return {
        "day": day.isoformat(),
        "number": game.puzzle_number(day),
        "time_limit": game.TIME_LIMIT_SECONDS,
        "meters_per_point": game.METERS_PER_POINT,
        "zones": [{"start": start, "name": name} for start, name in game.ZONES],
        "colleges": COLLEGES,
        "prompts": [{"id": p.id, "text": p.text, "hint": p.hint} for p in game.daily_prompts(day)],
    }


@app.post("/api/guess")
def guess(body: GuessIn):
    day = game.today()
    if body.prompt_id not in {p.id for p in game.daily_prompts(day)}:
        raise HTTPException(400, "That prompt isn't in today's set.")
    prompt = PROMPTS_BY_ID[body.prompt_id]
    key = day.isoformat()

    with db.connect() as conn:
        existing = conn.execute(
            "SELECT answer, points, share FROM guesses WHERE day = ? AND prompt_id = ? AND player_id = ?",
            (key, body.prompt_id, body.player_id),
        ).fetchone()
        if existing:
            answer, points, share = existing["answer"], existing["points"], existing["share"]
        else:
            answer = game.match_answer(prompt, body.answer)
            counts = _counts(conn, key, body.prompt_id)
            share = counts.get(answer, 0) / sum(counts.values()) if answer else 1.0
            points = game.score(share) if answer else 0
            if answer == prompt.golden:
                points += game.GOLDEN_BONUS
            conn.execute(
                "INSERT INTO guesses (day, prompt_id, player_id, raw, answer, points, share) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (key, body.prompt_id, body.player_id, body.answer, answer, points, share),
            )
        players = conn.execute(
            "SELECT COUNT(*) FROM guesses WHERE day = ? AND prompt_id = ?", (key, body.prompt_id)
        ).fetchone()[0]
        reveal = _reveal(_counts(conn, key, body.prompt_id), players)

    return {
        "valid": answer is not None,
        "answer": answer,
        "points": points,
        "share_pct": round(100 * share, 1) if answer else None,
        "rarity": game.rarity_label(share) if answer else None,
        "golden": answer is not None and answer == prompt.golden,
        "golden_answer": prompt.golden,
        **reveal,
    }


@app.post("/api/finish")
def finish(body: FinishIn):
    key = game.today().isoformat()
    college = body.college if body.college in COLLEGES else None
    with db.connect() as conn:
        total = conn.execute(
            "SELECT COALESCE(SUM(points), 0) FROM guesses WHERE day = ? AND player_id = ?", (key, body.player_id)
        ).fetchone()[0]
        conn.execute(
            "INSERT OR REPLACE INTO finishes (day, player_id, nickname, college, score) VALUES (?, ?, ?, ?, ?)",
            (key, body.player_id, body.nickname.strip(), college, total),
        )
        beaten = conn.execute("SELECT COUNT(*) FROM finishes WHERE day = ? AND score < ?", (key, total)).fetchone()[0]
        field = conn.execute("SELECT COUNT(*) FROM finishes WHERE day = ?", (key,)).fetchone()[0]
    percentile = round(100 * beaten / (field - 1)) if field > 1 else 100
    return {"score": total, "percentile": percentile, "players": field}


@app.get("/api/leaderboard")
def leaderboard():
    key = game.today().isoformat()
    with db.connect() as conn:
        players = conn.execute(
            "SELECT nickname, college, score FROM finishes WHERE day = ? ORDER BY score DESC LIMIT 15", (key,)
        ).fetchall()
        colleges = conn.execute(
            "SELECT college, ROUND(AVG(score)) AS avg, COUNT(*) AS n FROM finishes "
            "WHERE day = ? AND college IS NOT NULL GROUP BY college ORDER BY avg DESC",
            (key,),
        ).fetchall()
    return {"players": [dict(r) for r in players], "colleges": [dict(r) for r in colleges]}
