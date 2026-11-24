"""Use cases for playing a day: get the set, check and lock in answers, finish, see the standings."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

from ..domain import days, rules, scoring
from ..domain.matching import match_answer, recognize
from ..domain.models import Prompt, ScoredGuess
from ..domain.prompt_bank import PROMPTS
from .ports import Clock, PromptStats, UnitOfWork, UnitOfWorkFactory


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


@dataclass(frozen=True)
class PromptPreview:
    prompt: Prompt
    counts: dict[str, int]
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

    def preload(self) -> tuple[date, list[PromptPreview]]:
        """Load matching data and a rarity snapshot once, before play begins."""
        day = self._clock()
        with self._uow() as uow:
            prompts = prompts_for(uow, day)
            stats = uow.guesses.stats(day)  # every prompt's counts in one query
        empty = PromptStats()
        return day, [
            PromptPreview(p, scoring.answer_counts(p, stats.get(p.id, empty).tallies), stats.get(p.id, empty).players)
            for p in prompts
        ]

    def check(self, prompt_id: str, raw: str) -> CheckOutcome:
        """Before a guess counts: is it recognized, and is it right? Only right answers spend the prompt;
        wrong ones get another try until the clock runs out."""
        with self._uow() as uow:
            prompt = _find(prompts_for(uow, self._clock()), prompt_id)
        recognized, suggestion = recognize(prompt, raw)
        correct = recognized and match_answer(prompt, raw) is not None
        return CheckOutcome(recognized=recognized, correct=correct, suggestion=suggestion)

    def guess(self, player_id: str, prompt_id: str, raw: str) -> GuessOutcome:
        out = self._submit(player_id, prompt_id, raw, retry_wrong=False)
        assert isinstance(out, GuessOutcome)
        return out

    def attempt(self, player_id: str, prompt_id: str, raw: str) -> GuessOutcome | CheckOutcome:
        """Check and record a right answer in one transaction; wrong answers can retry."""
        return self._submit(player_id, prompt_id, raw, retry_wrong=True)

    def _submit(self, player_id: str, prompt_id: str, raw: str, *, retry_wrong: bool) -> GuessOutcome | CheckOutcome:
        day = self._clock()
        with self._uow() as uow:
            prompt = _find(prompts_for(uow, day), prompt_id)

            # A player's first guess on a prompt is final, so re-guessing can't farm points.
            scored = uow.guesses.find(day, prompt_id, player_id)
            if scored is None:
                answer = match_answer(prompt, raw)
                if retry_wrong:
                    recognized, suggestion = recognize(prompt, raw)
                    if not recognized or answer is None:
                        return CheckOutcome(recognized=recognized, correct=False, suggestion=suggestion)
                stats = uow.guesses.stats(day, prompt_id).get(prompt_id, PromptStats())
                before = scoring.answer_counts(prompt, stats.tallies)
                share = scoring.share_of(answer, before)
                scored = ScoredGuess(answer=answer, points=scoring.points_for(prompt, answer, before), share=share)
                if uow.guesses.add(day, prompt_id, player_id, raw, scored):
                    # Our row is the only change since the counts above, so update them here, not with a re-query.
                    tallies = dict(stats.tallies)
                    if answer is not None:
                        tallies[answer] = tallies.get(answer, 0) + 1
                    after = PromptStats(tallies, stats.players + 1)
                else:
                    after = uow.guesses.stats(day, prompt_id).get(prompt_id, PromptStats())
            else:
                after = uow.guesses.stats(day, prompt_id).get(prompt_id, PromptStats())

            counts = scoring.answer_counts(prompt, after.tallies)
            return GuessOutcome(prompt=prompt, guess=scored, reveal=scoring.reveal(counts, after.players, self._rng))

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
                    "points": scoring.points_for(prompt, name, counts),
                    "rarity": scoring.rarity_label(name, counts, golden),
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
