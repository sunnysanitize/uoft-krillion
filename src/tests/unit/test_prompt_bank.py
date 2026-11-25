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


def test_fallback_questions_have_room_for_rare_answers():
    assert all(len(p.answers) >= rules.MIN_ACCEPTED_ANSWERS for p in PROMPTS)
    assert not {
        "colleges",
        "theology_colleges",
        "alumni",
        "core_eight",
        "engsci_majors",
        "hart_house_committees",
    } & set(PROMPTS_BY_ID)


def test_broader_engineering_question_accepts_both_paths():
    prompt = PROMPTS_BY_ID["engineering_disciplines"]
    assert len(prompt.answers) == 17
    for name in ("Transportation Systems Engineering", "Mineral Engineering", "Machine Intelligence"):
        assert match_answer(prompt, name) == name
    assert match_answer(prompt, "TrackOne") is None
    assert match_answer(prompt, "Software Engineering") is None


def test_directory_questions_accept_familiar_short_names():
    libraries = PROMPTS_BY_ID["libraries"]
    assert match_answer(libraries, "robarts") == "Robarts Library"
    assert match_answer(libraries, "utm library") == "U of T Mississauga Library"
    assert match_answer(PROMPTS_BY_ID["faculties_divisions"], "oise") == "Ontario Institute for Studies in Education"
    assert match_answer(PROMPTS_BY_ID["utm_programs"], "ccit") == "Communication, Culture, Information and Technology"


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


def test_fallback_selection_excludes_small_questions():
    from tests.factories import COLLEGES

    day = date(2026, 11, 24)
    assert days.pick_fallback(day, [*PROMPTS, COLLEGES]) == days.pick_fallback(day, PROMPTS)
