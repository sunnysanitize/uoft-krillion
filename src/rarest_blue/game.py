"""Pure game logic: answer matching, daily prompt selection, rarity scoring."""

import difflib
import hashlib
import re
import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .prompts import PROMPTS, Prompt

TORONTO = ZoneInfo("America/Toronto")
LAUNCH_DATE = date(2026, 11, 1)
PROMPTS_PER_DAY = 7
TIME_LIMIT_SECONDS = 20
MAX_POINTS = 100
GOLDEN_BONUS = 100
METERS_PER_POINT = 10

# Depth zones, shallowest first: (starting depth in meters, name).
ZONES = [
    (0, "Philosopher's Walk Shallows"),
    (1000, "Sid Smith Drop-off"),
    (2500, "Bahen Trench"),
    (4000, "Robarts Abyss"),
    (6000, "The Steam Tunnels"),
]

_FILLER = {"the", "of", "and", "a", "at", "uoft", "u", "t"}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.lower().replace("&", " and ").replace("'", "")
    text = re.sub(r"\bst\b\.?", "saint", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(w for w in text.split() if w not in _FILLER)


def _alias_index(prompt: Prompt) -> dict[str, str]:
    index: dict[str, str] = {}
    for names in prompt.answers:
        for name in names:
            index.setdefault(normalize(name), names[0])
    return index


def match_answer(prompt: Prompt, guess: str) -> str | None:
    """Return the canonical answer the guess refers to, or None if invalid."""
    key = normalize(guess)
    if not key:
        return None
    index = _alias_index(prompt)
    if key in index:
        return index[key]
    # Forgive small typos on longer answers only, so "MAT" can't fuzz into "MAT137".
    if len(key) >= 5:
        close = difflib.get_close_matches(key, index.keys(), n=1, cutoff=0.85)
        if close:
            return index[close[0]]
    return None


def today() -> date:
    return datetime.now(TORONTO).date()


def puzzle_number(day: date) -> int:
    return (day - LAUNCH_DATE).days + 1


def daily_prompts(day: date) -> list[Prompt]:
    """Deterministically pick the day's prompts so everyone plays the same set."""
    def rank(p: Prompt) -> str:
        return hashlib.sha256(f"{day.isoformat()}:{p.id}".encode()).hexdigest()

    return sorted(PROMPTS, key=rank)[:PROMPTS_PER_DAY]


def prior_counts(prompt: Prompt) -> dict[str, int]:
    """Seed popularity from list order: the obvious answers start out common."""
    return {names[0]: max(1, round(60 / (i + 1))) for i, names in enumerate(prompt.answers)}


def score(share: float) -> int:
    """Points for an answer given the fraction of players who said the same thing."""
    return max(1, round(MAX_POINTS * (1 - share) ** 2))


def zone(depth_m: int) -> str:
    return [name for start, name in ZONES if depth_m >= start][-1]


def rarity_label(share: float) -> str:
    if share < 0.01:
        return "Legendary"
    if share < 0.05:
        return "Rare"
    if share < 0.15:
        return "Uncommon"
    if share < 0.35:
        return "Common"
    return "Basic"
