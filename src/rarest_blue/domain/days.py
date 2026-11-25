"""The game day runs on Toronto time."""

import hashlib
from datetime import date, datetime

from .models import Prompt
from .rules import LAUNCH_DATE, MIN_ACCEPTED_ANSWERS, PROMPTS_PER_DAY, TORONTO


def today() -> date:
    return datetime.now(TORONTO).date()


def puzzle_number(day: date) -> int:
    return (day - LAUNCH_DATE).days + 1


def pick_fallback(day: date, bank: list[Prompt]) -> list[Prompt]:
    """Deterministically pick a day's prompts from the built-in bank, for days the generator missed."""

    def rank(p: Prompt) -> str:
        return hashlib.sha256(f"{day.isoformat()}:{p.id}".encode()).hexdigest()

    eligible = [p for p in bank if len(p.answers) >= MIN_ACCEPTED_ANSWERS]
    if len(eligible) < PROMPTS_PER_DAY:
        raise ValueError(f"need {PROMPTS_PER_DAY} fallback prompts with at least {MIN_ACCEPTED_ANSWERS} answers")
    return sorted(eligible, key=rank)[:PROMPTS_PER_DAY]
