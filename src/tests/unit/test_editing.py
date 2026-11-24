from dataclasses import replace

from rarest_blue.application.editing import check_set, parse_set
from rarest_blue.domain import days
from rarest_blue.domain.prompt_bank import PROMPTS


def _day():
    from datetime import date

    return days.pick_fallback(date(2026, 11, 24), PROMPTS)


def test_fallback_set_has_no_errors():
    assert check_set(_day()).ok


def test_catches_what_would_break_the_day():
    prompts = _day()
    first, second = prompts[0], prompts[1]
    prompts[0] = replace(first, golden="Not an answer")
    prompts[1] = replace(second, decoys=[*second.decoys, second.answers[0][0]])
    report = check_set(prompts + [prompts[2]])
    assert any("golden 'Not an answer'" in e for e in report.errors)
    assert any("would score" in e for e in report.errors)
    assert any("need exactly" in e for e in report.errors)
    assert any("used twice" in e for e in report.errors)


def test_alias_shared_by_two_answers_is_an_error():
    p = _day()[0]
    answers = list(p.answers)
    answers[1] = (*answers[1], answers[0][0])
    report = check_set([replace(p, answers=answers)])
    assert any("belongs to both" in e for e in report.errors)


def test_parse_rejects_malformed_json():
    prompts, report = parse_set([{"id": "x"}, {"id": "y", "text": "t", "hint": "h", "golden": "g", "answers": [[1]]}])
    assert prompts == [] and len(report.errors) == 2
    assert not parse_set({"not": "a list"})[1].ok
