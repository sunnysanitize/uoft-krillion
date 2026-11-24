"""The game day runs on Toronto time."""

import hashlib
from datetime import date, datetime

from .models import Prompt
from .rules import LAUNCH_DATE, PROMPTS_PER_DAY, TORONTO


def today() -> date:
    return datetime.now(TORONTO).date()


def puzzle_number(day: date) -> int:
    return (day - LAUNCH_DATE).days + 1


def pick_fallback(day: date, bank: list[Prompt]) -> list[Prompt]:
    """Deterministically pick a day's prompts from the built-in bank, for days the generator missed."""

    def rank(p: Prompt) -> str:
        return hashlib.sha256(f"{day.isoformat()}:{p.id}".encode()).hexdigest()

    return sorted(bank, key=rank)[:PROMPTS_PER_DAY]
