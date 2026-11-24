from datetime import date

from rarest_blue.domain import days, rules
from rarest_blue.domain.matching import match_answer
from rarest_blue.domain.prompt_bank import PROMPTS


def test_fallback_prompts_have_decoys_that_dont_score():
    for p in PROMPTS:
        assert len(p.decoys) >= 8, f"{p.id}: needs decoys so autocomplete doesn't list only answers"
        for d in p.decoys:
            assert match_answer(p, d) is None, f"{p.id}: decoy '{d}' scores"


def test_golden_answers_are_valid_deep_cuts():
    for p in PROMPTS:
        names = p.canonical_answers
        assert p.golden in names, f"{p.id}: golden '{p.golden}' isn't an answer"
        assert names.index(p.golden) >= 3, f"{p.id}: golden answer is too obvious"


def test_fallback_prompts_are_stable_and_vary():
    d1, d2 = date(2026, 11, 23), date(2026, 11, 24)
    assert [p.id for p in days.pick_fallback(d1, PROMPTS)] == [p.id for p in days.pick_fallback(d1, PROMPTS)]
    assert len(days.pick_fallback(d1, PROMPTS)) == rules.PROMPTS_PER_DAY
    assert days.pick_fallback(d1, PROMPTS) != days.pick_fallback(d2, PROMPTS)


def test_prompt_round_trips_through_dict():
    for p in PROMPTS:
        assert type(p).from_dict(p.to_dict()) == p
