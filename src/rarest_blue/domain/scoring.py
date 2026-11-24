"""Rarity scoring: the fewer players who gave your answer, the more it's worth."""

import random

from .models import Prompt
from .rules import GOLDEN, GOLDEN_POINTS, TIER_POINTS

TOP_ANSWERS_SHOWN = 6
DEEP_CUTS_SHOWN = 3


def prior_counts(prompt: Prompt) -> dict[str, int]:
    """Seed popularity from list order, so the obvious answers start out common."""
    return {names[0]: max(1, round(60 / (i + 1))) for i, names in enumerate(prompt.answers)}


def answer_counts(prompt: Prompt, tallies: dict[str, int]) -> dict[str, int]:
    """How often each answer counts as given: the list-order priors plus real guesses."""
    counts = prior_counts(prompt)
    for answer, n in tallies.items():
        counts[answer] = counts.get(answer, 0) + n
    return counts


def score(share: float, golden: bool = False) -> int:
    """Points for a valid answer, from the fraction of players who said the same thing."""
    return GOLDEN_POINTS if golden else TIER_POINTS[rarity_label(share)]


def points_for(prompt: Prompt, answer: str | None, share: float) -> int:
    return score(share, answer == prompt.golden) if answer is not None else 0


def share_of(answer: str | None, counts: dict[str, int]) -> float:
    return counts.get(answer, 0) / sum(counts.values()) if answer else 1.0


def rarity_label(share: float, golden: bool = False) -> str:
    if golden:
        return GOLDEN
    if share < 0.05:
        return "Deep Cut"
    if share < 0.15:
        return "Rare"
    if share < 0.35:
        return "Uncommon"
    return "Common"


def reveal(counts: dict[str, int], players: int, rng: random.Random | None = None) -> dict:
    """What a player sees after answering: the popular answers and a few deep cuts to learn for tomorrow."""
    rng = rng or random
    total = sum(counts.values())
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    top = [{"answer": a, "pct": round(100 * n / total, 1)} for a, n in ranked[:TOP_ANSWERS_SHOWN]]
    deep_cuts = [a for a, _ in ranked[len(ranked) // 2 :]]
    rng.shuffle(deep_cuts)
    return {"top": top, "deep_cuts": deep_cuts[:DEEP_CUTS_SHOWN], "players": players, "valid_answers": len(counts)}
