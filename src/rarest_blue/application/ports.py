"""Ports: the interfaces the use cases need from the outside world.

Infrastructure implements them (Postgres, OpenRouter). Tests can swap in fakes. Nothing here knows about SQL or HTTP.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Protocol

from ..domain.models import Prompt, ScoredGuess


class PromptRepository(Protocol):
    def get(self, day: date) -> list[Prompt] | None: ...

    def add(self, day: date, prompts: list[Prompt], source: str) -> bool:
        """Store a day's set. Returns False if the day already has one (first write wins)."""
        ...

    def replace_prompt(self, day: date, prompt: Prompt) -> None: ...

    def recent_texts(self, before: date, days: int) -> list[str]: ...


class GuessRepository(Protocol):
    def find(self, day: date, prompt_id: str, player_id: str) -> ScoredGuess | None: ...

    def add(self, day: date, prompt_id: str, player_id: str, raw: str, guess: ScoredGuess) -> None:
        """Record a guess. A second guess by the same player on the same prompt is ignored."""
        ...

    def tallies(self, day: date, prompt_id: str) -> dict[str, int]:
        """How many players gave each valid answer."""
        ...

    def player_count(self, day: date, prompt_id: str) -> int: ...

    def player_total(self, day: date, player_id: str) -> int: ...

    def rejected(self, day: date) -> list[tuple[str, str]]:
        """(prompt_id, raw) for every guess that matched no answer."""
        ...

    def unmatched(self, day: date, prompt_id: str) -> list[tuple[str, str]]:
        """(player_id, raw) for every guess on a prompt that matched no answer."""
        ...

    def set_answer(self, day: date, prompt_id: str, player_id: str, answer: str) -> None: ...

    def set_score(self, day: date, prompt_id: str, player_id: str, points: int, share: float) -> None: ...

    def delete_player(self, day: date, player_id: str) -> None: ...


class FinishRepository(Protocol):
    def upsert(self, day: date, player_id: str, nickname: str, score: int) -> None: ...

    def count_below(self, day: date, score: int) -> int: ...

    def count(self, day: date) -> int: ...

    def top(self, day: date, limit: int) -> list[dict]: ...

    def recompute_scores(self, day: date, player_ids: list[str]) -> None:
        """Reset these players' totals to the sum of their guesses' points."""
        ...

    def delete_player(self, day: date, player_id: str) -> None: ...


class UnitOfWork(Protocol):
    """One transaction: commits on a clean exit, rolls back on an exception."""

    prompts: PromptRepository
    guesses: GuessRepository
    finishes: FinishRepository

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(self, *exc) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
Clock = Callable[[], date]


class PromptWriter(Protocol):
    """Something that writes a prompt set from instructions: in production, an LLM."""

    def write(self, request: str, model: str, response_schema: dict) -> str:
        """Returns the raw JSON text of the reply."""
        ...
