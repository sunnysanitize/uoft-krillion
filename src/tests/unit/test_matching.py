from rarest_blue.domain.matching import match_answer, normalize, recognize
from rarest_blue.domain.prompt_bank import PROMPTS, PROMPTS_BY_ID


def test_aliases_and_typos_match():
    colleges = PROMPTS_BY_ID["colleges"]
    assert match_answer(colleges, "Vic") == "Victoria College"
    assert match_answer(colleges, "st. mike's") == "St. Michael's College"
    assert match_answer(colleges, "Woodsworht") == "Woodsworth College"
    assert match_answer(colleges, "Ryerson") is None
    assert match_answer(colleges, "   ") is None


def test_short_codes_do_not_fuzz():
    courses = PROMPTS_BY_ID["first_year_pain"]
    assert match_answer(courses, "mat137") == "MAT137"
    assert match_answer(courses, "MAT") is None


def test_short_forms_and_extra_words_match():
    buildings = PROMPTS_BY_ID["buildings"]
    assert match_answer(buildings, "Lash Miller Chemical") == "Lash Miller Chemical Laboratories"
    assert match_answer(buildings, "Koffler Student") == "Koffler Student Services Centre"
    assert match_answer(PROMPTS_BY_ID["subway"], "Spadina Station") == "Spadina"
    assert match_answer(PROMPTS_BY_ID["libraries"], "Innis Library") == "Innis College Library"
    # Ambiguous or generic leading words don't count.
    assert match_answer(PROMPTS_BY_ID["ontario_unis"], "University") is None
    assert match_answer(PROMPTS_BY_ID["faculties"], "Faculty") is None


def test_no_alias_collisions_within_a_prompt():
    for p in PROMPTS:
        seen: dict[str, str] = {}
        for names in p.answers:
            for name in names:
                key = normalize(name)
                assert seen.setdefault(key, names[0]) == names[0], f"{p.id}: '{name}' collides"


def test_recognize_treats_answers_and_decoys_alike():
    colleges = PROMPTS_BY_ID["colleges"]
    assert recognize(colleges, "vic") == (True, None)
    assert recognize(colleges, "Massey College") == (True, None)
    # Typos of either kind are suggested, never silently accepted.
    assert recognize(colleges, "Woodsworht") == (False, "Woodsworth College")
    assert recognize(colleges, "Masey College") == (False, "Massey College")
    assert recognize(colleges, "Ryerson Hall") == (False, None)
