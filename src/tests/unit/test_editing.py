from dataclasses import replace
from datetime import date, timedelta

import pytest

from rarest_blue.application.editing import (
    Change,
    apply_change,
    check_set,
    commit_change,
    parse_set,
    preview_change,
)
from rarest_blue.application.ports import PromptStats
from rarest_blue.domain import days
from rarest_blue.domain.matching import match_answer
from rarest_blue.domain.prompt_bank import PROMPTS


def _day():
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


# --- Reviewer changes ----------------------------------------------------------------------------------------------

TODAY = date(2026, 11, 25)
TOMORROW = TODAY + timedelta(days=1)


class _Prompts:
    def __init__(self, sets):
        self.sets = sets

    def get(self, day):
        return self.sets.get(day)

    def replace_prompt(self, day, prompt):
        self.sets[day] = [prompt if p.id == prompt.id else p for p in self.sets[day]]


class _Guesses:
    def __init__(self, players=0):
        self.players = players

    def stats(self, day, prompt_id=None):
        return {"any": PromptStats(players=self.players)}

    def unmatched(self, day, prompt_id):
        return []


class _Uow:
    """Just enough of a unit of work for changes: stored sets, and whether anyone has guessed yet."""

    def __init__(self, day=TOMORROW, players=0):
        self.prompts = _Prompts({day: _day()})
        self.guesses = _Guesses(players)


def _first(uow, day=TOMORROW):
    return uow.prompts.get(day)[0]


def test_change_round_trips_through_dict():
    change = Change("add_answer", "p", "Name", aliases=("a", "b"))
    assert Change.from_dict(change.to_dict()) == change
    assert Change.from_dict(Change("remove_decoy", "p", "X").to_dict()) == Change("remove_decoy", "p", "X")


def test_new_answer_goes_just_before_the_golden():
    p = _day()[0]
    updated = apply_change(p, Change("add_answer", p.id, "Brand New Thing", aliases=("bnt",)))
    canon = updated.canonical_answers
    assert canon[canon.index(updated.golden) - 1] == "Brand New Thing"
    assert match_answer(updated, "bnt") == "Brand New Thing"


def test_changes_refuse_what_doesnt_make_sense():
    p = _day()[0]
    taken = p.answers[0][0]
    with pytest.raises(ValueError, match="already counts"):
        apply_change(p, Change("add_answer", p.id, taken))
    with pytest.raises(ValueError, match="already counts"):
        apply_change(p, Change("add_alias", p.id, p.answers[1][0], text=taken))
    with pytest.raises(ValueError, match="isn't an answer"):
        apply_change(p, Change("remove_answer", p.id, "Not a real answer"))
    with pytest.raises(ValueError, match="pick a new golden first"):
        apply_change(p, Change("remove_answer", p.id, p.golden))
    with pytest.raises(ValueError, match="isn't a decoy"):
        apply_change(p, Change("remove_decoy", p.id, "Not a decoy"))


def test_adding_a_decoy_as_an_answer_drops_the_decoy():
    p = _day()[0]
    decoy = p.decoys[0]
    updated = apply_change(p, Change("add_answer", p.id, decoy))
    assert decoy not in updated.decoys and match_answer(updated, decoy) == decoy


def test_new_golden_drops_the_old_explanation_unless_given_one():
    p = replace(_day()[0], golden_why="About the old golden.")
    other = p.canonical_answers[-1] if p.canonical_answers[-1] != p.golden else p.canonical_answers[-2]
    assert apply_change(p, Change("set_golden", p.id, other)).golden_why == ""
    assert apply_change(p, Change("set_golden", p.id, other, text="Why.")).golden_why == "Why."
    assert apply_change(p, Change("set_golden", p.id, p.golden)).golden_why == "About the old golden."


def test_commit_stores_a_change_before_the_day_goes_live():
    uow = _Uow()
    decoy = _first(uow).decoys[0]
    assert commit_change(uow, TOMORROW, TODAY, Change("remove_decoy", _first(uow).id, decoy)) == 0
    assert decoy not in _first(uow).decoys


def test_live_day_only_takes_additions():
    for day, players in [(TODAY, 0), (TOMORROW, 3)]:  # today's set, or a later one someone already guessed on
        uow = _Uow(day, players)
        p = _first(uow, day)
        with pytest.raises(ValueError, match="already being played"):
            preview_change(uow, day, TODAY, Change("remove_answer", p.id, p.answers[0][0]))
        commit_change(uow, day, TODAY, Change("add_alias", p.id, p.answers[0][0], text="totally new alias"))
        assert match_answer(_first(uow, day), "totally new alias") == p.answers[0][0]


def test_commit_refuses_a_change_that_breaks_the_day():
    uow = _Uow()
    p = _first(uow)
    uow.prompts.sets[TOMORROW][1] = replace(uow.prompts.sets[TOMORROW][1], id=p.id)  # already broken: duplicate id
    with pytest.raises(ValueError, match="used twice"):
        commit_change(uow, TOMORROW, TODAY, Change("remove_decoy", p.id, p.decoys[0]))


def test_unknown_day_or_prompt_is_a_clear_error():
    uow = _Uow()
    with pytest.raises(ValueError, match="no stored set"):
        preview_change(uow, TOMORROW + timedelta(days=5), TODAY, Change("remove_decoy", "x", "y"))
    with pytest.raises(ValueError, match="no prompt 'nope'"):
        preview_change(uow, TOMORROW, TODAY, Change("remove_decoy", "nope", "y"))
