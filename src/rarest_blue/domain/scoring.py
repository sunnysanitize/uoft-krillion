"""Rarity scoring: the fewer players who gave your answer, the more it's worth."""

import random

from .models import Prompt
from .rules import GOLDEN, GOLDEN_POINTS, TIER_CUTOFFS, TIER_POINTS

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


def popularity_above(answer: str, counts: dict[str, int]) -> float:
    """Fraction of all picks that went to answers strictly more popular than this one (0 = the most popular)."""
    total = sum(counts.values())
    mine = counts.get(answer, 0)
    return sum(n for n in counts.values() if n > mine) / total if total else 0.0


def rarity_label(answer: str, counts: dict[str, int], golden: bool = False) -> str:
    if golden:
        return GOLDEN
    above = popularity_above(answer, counts)
    return next((label for cutoff, label in TIER_CUTOFFS if above < cutoff), "Deep Cut")


def points_for(prompt: Prompt, answer: str | None, counts: dict[str, int]) -> int:
    """Points for a guess, given how often each answer has been picked so far (priors included)."""
    if answer is None:
        return 0
    return TIER_POINTS[rarity_label(answer, counts)] if answer != prompt.golden else GOLDEN_POINTS


def label_for_points(points: int, golden: bool) -> str:
    """The tier a stored score was awarded at."""
    if golden:
        return GOLDEN
    return next((label for label, p in TIER_POINTS.items() if p == points), "Common")


def share_of(answer: str | None, counts: dict[str, int]) -> float:
    return counts.get(answer, 0) / sum(counts.values()) if answer else 1.0


def reveal(counts: dict[str, int], players: int, rng: random.Random | None = None) -> dict:
    """What a player sees after answering: the popular answers and a few deep cuts to learn for tomorrow."""
    rng = rng or random
    total = sum(counts.values())
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    top = [{"answer": a, "pct": round(100 * n / total, 1)} for a, n in ranked[:TOP_ANSWERS_SHOWN]]
    deep_cuts = [a for a, _ in ranked[len(ranked) // 2 :]]
    rng.shuffle(deep_cuts)
    return {"top": top, "deep_cuts": deep_cuts[:DEEP_CUTS_SHOWN], "players": players, "valid_answers": len(counts)}
