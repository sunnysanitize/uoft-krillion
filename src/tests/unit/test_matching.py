import json
from pathlib import Path

from rarest_blue.domain.matching import match_answer, normalize, recognize
from rarest_blue.domain.models import Prompt
from rarest_blue.domain.prompt_bank import PROMPTS, PROMPTS_BY_ID


def test_shared_browser_matching_fixture_tracks_server_rules():
    fixture = json.loads((Path(__file__).resolve().parents[1] / "fixtures/local_matching.json").read_text())
    prompt = Prompt.from_dict(fixture["prompt"])
    for case in fixture["cases"]:
        raw = case["raw"]
        recognized, suggestion = recognize(prompt, raw)
        answer = match_answer(prompt, raw)
        assert normalize(raw) == case["normalized"]
        assert answer == case["answer"]
        assert case["check"] == {
            "recognized": recognized,
            "correct": recognized and answer is not None,
            "suggestion": suggestion,
        }


def test_aliases_and_typos_match():
    colleges = PROMPTS_BY_ID["colleges"]
    assert match_answer(colleges, "Vic") == "Victoria College"
    assert match_answer(colleges, "st. mike's") == "St. Michael's College"
    assert match_answer(colleges, "Woodsworht") == "Woodsworth College"
    assert match_answer(colleges, "Ryerson") is None
    assert match_answer(colleges, "   ") is None


def test_short_codes_do_not_fuzz():
    courses = Prompt("codes", "Course codes", "", "MAT157", [("MAT137",), ("MAT157",)])
    assert match_answer(courses, "mat137") == "MAT137"
    assert match_answer(courses, "MAT") is None


def test_short_forms_and_extra_words_match():
    buildings = Prompt(
        "places",
        "Places",
        "",
        "Innis College Library",
        [
            ("Lash Miller Chemical Laboratories",),
            ("Koffler Student Services Centre",),
            ("Spadina",),
            ("Innis College Library", "innis"),
            ("University College",),
            ("University Library",),
        ],
    )
    assert match_answer(buildings, "Lash Miller Chemical") == "Lash Miller Chemical Laboratories"
    assert match_answer(buildings, "Koffler Student") == "Koffler Student Services Centre"
    assert match_answer(buildings, "Spadina Station") == "Spadina"
    assert match_answer(buildings, "Innis Library") == "Innis College Library"
    # Ambiguous or generic leading words don't count.
    assert match_answer(buildings, "University") is None
    assert match_answer(buildings, "Faculty") is None


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
