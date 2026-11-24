"""Use cases for playing a day: get the set, check and lock in answers, finish, see the standings."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

from ..domain import days, rules, scoring
from ..domain.matching import match_answer, recognize
from ..domain.models import Prompt, ScoredGuess
from ..domain.prompt_bank import PROMPTS
from .ports import Clock, UnitOfWork, UnitOfWorkFactory


class UnknownPrompt(LookupError):
    """The prompt id isn't in today's set."""


class NotPlayedYet(PermissionError):
    """The player asked for a prompt's answers before answering it."""


@dataclass(frozen=True)
class CheckOutcome:
    recognized: bool
    correct: bool
    suggestion: str | None


@dataclass(frozen=True)
class GuessOutcome:
    prompt: Prompt
    guess: ScoredGuess
    reveal: dict

    @property
    def valid(self) -> bool:
        return self.guess.answer is not None

    @property
    def golden(self) -> bool:
        return self.valid and self.guess.answer == self.prompt.golden


@dataclass(frozen=True)
class FinishOutcome:
    score: int
    percentile: int
    players: int


def prompts_for(uow: UnitOfWork, day: date) -> list[Prompt]:
    """The day's set: whatever the nightly job stored, else the built-in fallback.

    The fallback is stored on first use so the day's set can't change mid-day.
    """
    prompts = uow.prompts.get(day)
    if prompts is None:
        uow.prompts.add(day, days.pick_fallback(day, PROMPTS), source="fallback")
        prompts = uow.prompts.get(day)
    return prompts


class GameService:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock = days.today, rng: random.Random | None = None):
        self._uow = uow
        self._clock = clock
        self._rng = rng

    def daily(self) -> tuple[date, list[Prompt]]:
        day = self._clock()
        with self._uow() as uow:
            return day, prompts_for(uow, day)

    def check(self, prompt_id: str, raw: str) -> CheckOutcome:
        """Before a guess counts: is it recognized, and is it right? Only right answers spend the prompt;
        wrong ones get another try until the clock runs out."""
        with self._uow() as uow:
            prompt = _find(prompts_for(uow, self._clock()), prompt_id)
        recognized, suggestion = recognize(prompt, raw)
        correct = recognized and match_answer(prompt, raw) is not None
        return CheckOutcome(recognized=recognized, correct=correct, suggestion=suggestion)

    def guess(self, player_id: str, prompt_id: str, raw: str) -> GuessOutcome:
        day = self._clock()
        with self._uow() as uow:
            prompt = _find(prompts_for(uow, day), prompt_id)

            # A player's first guess on a prompt is final, so re-guessing can't farm points.
            scored = uow.guesses.find(day, prompt_id, player_id)
            if scored is None:
                answer = match_answer(prompt, raw)
                share = scoring.share_of(answer, scoring.answer_counts(prompt, uow.guesses.tallies(day, prompt_id)))
                scored = ScoredGuess(answer=answer, points=scoring.points_for(prompt, answer, share), share=share)
                uow.guesses.add(day, prompt_id, player_id, raw, scored)

            players = uow.guesses.player_count(day, prompt_id)
            counts = scoring.answer_counts(prompt, uow.guesses.tallies(day, prompt_id))
            return GuessOutcome(prompt=prompt, guess=scored, reveal=scoring.reveal(counts, players, self._rng))

    def answers(self, player_id: str, prompt_id: str) -> list[dict]:
        """Every valid answer to a prompt with its share and points right now, rarest first.

        Only for a player who has already answered (or run out of air on) that prompt today.
        """
        day = self._clock()
        with self._uow() as uow:
            prompt = _find(prompts_for(uow, day), prompt_id)
            played = uow.guesses.find(day, prompt_id, player_id)
            if played is None:
                raise NotPlayedYet(prompt_id)
            counts = scoring.answer_counts(prompt, uow.guesses.tallies(day, prompt_id))
        total = sum(counts.values())
        rows = []
        for name in prompt.canonical_answers:
            share = counts.get(name, 0) / total
            golden = name == prompt.golden
            rows.append(
                {
                    "answer": name,
                    "pct": round(100 * share, 1),
                    "points": scoring.score(share, golden),
                    "rarity": scoring.rarity_label(share, golden),
                    "golden": golden,
                    "yours": name == played.answer,
                }
            )
        rows.sort(key=lambda r: (-r["points"], r["pct"], r["answer"]))
        return rows

    def finish(self, player_id: str, nickname: str) -> FinishOutcome:
        day = self._clock()
        with self._uow() as uow:
            total = uow.guesses.player_total(day, player_id)
            uow.finishes.upsert(day, player_id, nickname.strip(), total)
            beaten = uow.finishes.count_below(day, total)
            field = uow.finishes.count(day)
        percentile = round(100 * beaten / (field - 1)) if field > 1 else 100
        return FinishOutcome(score=total, percentile=percentile, players=field)

    def leaderboard(self) -> list[dict]:
        with self._uow() as uow:
            return uow.finishes.top(self._clock(), rules.LEADERBOARD_SIZE)

    def reset_player(self, player_id: str) -> None:
        """Local testing only: forget a player's day so they can replay it."""
        day = self._clock()
        with self._uow() as uow:
            uow.guesses.delete_player(day, player_id)
            uow.finishes.delete_player(day, player_id)


def _find(prompts: list[Prompt], prompt_id: str) -> Prompt:
    prompt = next((p for p in prompts if p.id == prompt_id), None)
    if prompt is None:
        raise UnknownPrompt(prompt_id)
    return prompt
