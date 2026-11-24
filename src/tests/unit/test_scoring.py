import random

import pytest

from rarest_blue.domain import scoring
from rarest_blue.domain.models import Prompt
from rarest_blue.domain.prompt_bank import PROMPTS_BY_ID


def test_rarer_scores_higher():
    assert [scoring.score(s) for s in (0.005, 0.02, 0.06, 0.2)] == [85, 60, 30, 10]
    assert scoring.score(0.6, golden=True) == 100


def test_rarity_tiers():
    labels = [scoring.rarity_label(s) for s in (0.005, 0.02, 0.06, 0.25, 0.6)]
    assert labels == ["Deep Cut", "Rare", "Uncommon", "Common", "Common"]
    assert scoring.rarity_label(0.6, golden=True) == "One in a Krillion"


@pytest.mark.parametrize(
    ("share", "points"),
    [(0.0099, 85), (0.01, 60), (0.0299, 60), (0.03, 30), (0.0999, 30), (0.10, 10)],
)
def test_rarity_boundaries(share, points):
    assert scoring.score(share) == points


def test_obvious_answers_in_large_categories_start_common():
    prompt = Prompt("large", "Large category", "", "Answer 69", [(f"Answer {i}",) for i in range(70)])
    counts = scoring.answer_counts(prompt, {})
    assert scoring.points_for(prompt, "Answer 0", scoring.share_of("Answer 0", counts)) == 10
    assert scoring.points_for(prompt, "Answer 1", scoring.share_of("Answer 1", counts)) == 10
    # Knowing any valid answer is not enough to earn Rare or Deep Cut.
    assert scoring.points_for(prompt, "Answer 3", scoring.share_of("Answer 3", counts)) == 30


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
