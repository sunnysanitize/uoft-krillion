import random

import pytest

from rarest_blue.domain import scoring
from rarest_blue.domain.models import Prompt
from rarest_blue.domain.prompt_bank import PROMPTS_BY_ID


def _list(n: int) -> Prompt:
    return Prompt("p", "Name one", "", f"Answer {n - 1}", [(f"Answer {i}",) for i in range(n)])


def _tiers(n: int) -> list[str]:
    p = _list(n)
    counts = scoring.answer_counts(p, {})
    return [scoring.rarity_label(a, counts) for a in p.canonical_answers]


def test_obvious_answers_start_common_and_tail_is_rare():
    tiers = _tiers(30)
    assert tiers[:4] == ["Common"] * 4  # the obvious ones are worth little
    assert tiers[4:9] == ["Uncommon"] * 5  # knowing the 9th answer isn't "Rare"
    assert tiers[-1] == "Deep Cut"
    assert tiers == sorted(tiers, key=["Common", "Uncommon", "Rare", "Deep Cut"].index)


@pytest.mark.parametrize("n", [7, 20, 40, 70])
def test_long_lists_are_not_more_generous(n):
    tiers = _tiers(n)
    rare_or_better = sum(t in ("Rare", "Deep Cut") for t in tiers) / n
    assert tiers[0] == "Common" and tiers[1] == "Common"
    assert rare_or_better <= 0.6  # most of any list is Common/Uncommon at the start of a day
    assert tiers[-1] in ("Rare", "Deep Cut")


def test_real_guesses_move_answers_between_tiers():
    p = _list(20)
    deep = "Answer 18"
    assert scoring.rarity_label(deep, scoring.answer_counts(p, {})) == "Deep Cut"
    # Once lots of players pick it, it's no longer rare.
    assert scoring.rarity_label(deep, scoring.answer_counts(p, {deep: 200})) == "Common"


def test_points_and_labels_agree():
    p = _list(30)
    counts = scoring.answer_counts(p, {})
    for a in p.canonical_answers:
        pts = scoring.points_for(p, a, counts)
        assert scoring.label_for_points(pts, a == p.golden) == scoring.rarity_label(a, counts, a == p.golden)
    assert scoring.points_for(p, p.golden, counts) == 100
    assert scoring.label_for_points(100, True) == "One in a Krillion"


def test_golden_and_invalid_points():
    colleges = PROMPTS_BY_ID["colleges"]
    counts = scoring.answer_counts(colleges, {})
    assert scoring.points_for(colleges, None, counts) == 0
    assert scoring.points_for(colleges, colleges.golden, counts) == 100


def test_answer_counts_add_tallies_to_priors():
    colleges = PROMPTS_BY_ID["colleges"]
    priors = scoring.prior_counts(colleges)
    counts = scoring.answer_counts(colleges, {"Innis College": 3})
    assert counts["Innis College"] == priors["Innis College"] + 3
    assert counts["Trinity College"] == priors["Trinity College"]


def test_reveal_is_deterministic_with_a_seeded_rng():
    counts = {f"a{i}": 10 - i for i in range(10)}
    first = scoring.reveal(counts, 4, random.Random(1))
    assert first == scoring.reveal(counts, 4, random.Random(1))
    assert [t["answer"] for t in first["top"]] == ["a0", "a1", "a2", "a3", "a4", "a5"]
    assert len(first["deep_cuts"]) == 3 and first["valid_answers"] == 10 and first["players"] == 4
