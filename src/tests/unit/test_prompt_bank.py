from datetime import date

from rarest_blue.domain import days, rules
from rarest_blue.domain.matching import match_answer
from rarest_blue.domain.prompt_bank import PROMPT_SOURCES, PROMPTS, PROMPTS_BY_ID


def test_bank_has_sources_unique_ids_and_spare_questions():
    assert len(PROMPTS_BY_ID) == len(PROMPTS) > rules.PROMPTS_PER_DAY
    assert set(PROMPT_SOURCES) == set(PROMPTS_BY_ID)
    assert all(PROMPT_SOURCES.values())


def test_every_accepted_name_matches_its_own_answer():
    for prompt in PROMPTS:
        for names in prompt.answers:
            for name in names:
                assert match_answer(prompt, name) == names[0], (prompt.id, name)


def test_college_questions_distinguish_membership_from_theology():
    artsci = PROMPTS_BY_ID["colleges"]
    theology = PROMPTS_BY_ID["theology_colleges"]
    assert "Arts & Science" in artsci.text and len(artsci.answers) == 7
    assert "Toronto School of Theology" in theology.text and len(theology.answers) == 7
    for name in ("Knox", "Wycliffe", "Emmanuel", "Regis"):
        assert match_answer(theology, name) is not None
        assert match_answer(artsci, name) is None
    assert match_answer(theology, "St. Augustine's Seminary") == "St. Augustine's Seminary"
    assert match_answer(theology, "Massey") is None


def test_engsci_includes_transportation_and_separates_core_eight():
    engsci = PROMPTS_BY_ID["engsci_majors"]
    core = PROMPTS_BY_ID["core_eight"]
    assert len(engsci.answers) == 9 and len(core.answers) == 8
    assert match_answer(engsci, "Transportation Systems Engineering") == "Transportation Systems Engineering"
    assert match_answer(core, "Mineral Engineering") == "Mineral Engineering"
    assert match_answer(core, "Machine Intelligence") is None
    assert match_answer(engsci, "Mineral Engineering") is None


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
