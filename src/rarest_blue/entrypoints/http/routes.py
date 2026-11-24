"""HTTP routes. Thin: parse the request, call a use case, shape the response the web app expects."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from ...application.gameplay import GameService, NotPlayedYet, UnknownPrompt
from ...domain import days, rules, scoring
from .schemas import CheckIn, FinishIn, GuessIn, PlayerIn, PlayerPromptIn

router = APIRouter(prefix="/api")
# Mounted only when DEV_RESET=1 (see app.py). Never in production.
dev_router = APIRouter(prefix="/api/dev")

UNKNOWN_PROMPT = "That prompt isn't in today's set."


def get_game(request: Request) -> GameService:
    return request.app.state.game


Game = Annotated[GameService, Depends(get_game)]


@router.get("/daily")
def daily(game: Game):
    day, prompts = game.daily()
    return {
        "day": day.isoformat(),
        "number": days.puzzle_number(day),
        "time_limit": rules.TIME_LIMIT_SECONDS,
        "meters_per_point": rules.METERS_PER_POINT,
        "zones": [{"start": start, "name": name} for start, name in rules.ZONES],
        # Never the answers: the browser only ever sees the question.
        "prompts": [{"id": p.id, "text": p.text, "hint": p.hint} for p in prompts],
    }


@router.post("/check")
def check(body: CheckIn, game: Game):
    try:
        out = game.check(body.prompt_id, body.answer)
    except UnknownPrompt:
        raise HTTPException(400, UNKNOWN_PROMPT) from None
    return {"recognized": out.recognized, "correct": out.correct, "suggestion": out.suggestion}


@router.post("/guess")
def guess(body: GuessIn, game: Game):
    try:
        out = game.guess(body.player_id, body.prompt_id, body.answer)
    except UnknownPrompt:
        raise HTTPException(400, UNKNOWN_PROMPT) from None
    g = out.guess
    return {
        "valid": out.valid,
        "answer": g.answer,
        "points": g.points,
        "share_pct": round(100 * g.share, 1) if out.valid else None,
        "rarity": scoring.rarity_label(g.share, out.golden) if out.valid else None,
        "golden": out.golden,
        "golden_answer": out.prompt.golden,
        **out.reveal,
    }


@router.post("/answers")
def answers(body: PlayerPromptIn, game: Game):
    try:
        rows = game.answers(body.player_id, body.prompt_id)
    except UnknownPrompt:
        raise HTTPException(400, UNKNOWN_PROMPT) from None
    except NotPlayedYet:
        raise HTTPException(403, "Answer this prompt first.") from None
    return {"answers": rows}


@router.post("/finish")
def finish(body: FinishIn, game: Game):
    out = game.finish(body.player_id, body.nickname)
    return {"score": out.score, "percentile": out.percentile, "players": out.players}


@router.get("/leaderboard")
def leaderboard(game: Game):
    return {"players": game.leaderboard()}


@dev_router.post("/reset")
def dev_reset(body: PlayerIn, game: Game):
    game.reset_player(body.player_id)
    return {"ok": True}
