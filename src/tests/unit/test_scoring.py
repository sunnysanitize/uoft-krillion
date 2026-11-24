import random

from rarest_blue.domain import scoring
from rarest_blue.domain.prompt_bank import PROMPTS_BY_ID


def test_rarer_scores_higher():
    assert [scoring.score(s) for s in (0.01, 0.1, 0.2, 0.6)] == [85, 60, 30, 10]
    assert scoring.score(0.6, golden=True) == 100


def test_rarity_tiers():
    labels = [scoring.rarity_label(s) for s in (0.005, 0.03, 0.1, 0.25, 0.6)]
    assert labels == ["Deep Cut", "Deep Cut", "Rare", "Uncommon", "Common"]
    assert scoring.rarity_label(0.6, golden=True) == "One in a Krillion"


def test_golden_and_invalid_points():
    colleges = PROMPTS_BY_ID["colleges"]
    assert scoring.points_for(colleges, None, 1.0) == 0
    assert scoring.points_for(colleges, colleges.golden, 0.5) == 100


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
