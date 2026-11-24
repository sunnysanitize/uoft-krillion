import pytest

from rarest_blue.application import review
from rarest_blue.domain.matching import match_answer
from rarest_blue.domain.prompt_bank import PROMPTS_BY_ID


def test_accept_as_alias_checks_the_answer():
    colleges = PROMPTS_BY_ID["colleges"]
    updated = review.with_answer(colleges, "Woody C", "woodsworth")
    assert match_answer(updated, "woody c") == "Woodsworth College"
    with pytest.raises(ValueError, match="isn't an answer"):
        review.with_answer(colleges, "Woody C", "Ryerson")
    with pytest.raises(ValueError, match="already counts"):
        review.with_answer(colleges, "vic", "Trinity")


class _Guesses:
    def __init__(self, rows):
        self.rows = rows

    def rejected(self, day):
        return self.rows


class _Prompts:
    def __init__(self, prompts):
        self.prompts = prompts

    def get(self, day):
        return self.prompts


class _Uow:
    def __init__(self, prompts, rows):
        self.prompts, self.guesses = _Prompts(prompts), _Guesses(rows)


class _Writer:
    def __init__(self, rulings):
        self.rulings, self.requests = rulings, []

    def write(self, request, model, response_schema, temperature):
        self.requests.append(request)
        return review.Rulings.model_validate(self.rulings).model_dump_json()


def test_judge_only_accepts_typed_guesses_and_known_aliases():
    colleges = PROMPTS_BY_ID["colleges"]
    uow = _Uow([colleges], [("colleges", "Woody C"), ("colleges", "sh"), ("colleges", "Massey")])
    writer = _Writer({"prompts": [{"id": "colleges", "rulings": [
        {"guess": "Woody C", "valid": True, "same_as": "Woodsworth College", "new_name": ""},
        {"guess": "Massey", "valid": True, "same_as": "Not An Answer", "new_name": "Massey College"},
        {"guess": "Invented", "valid": True, "same_as": "", "new_name": "Invented"},
        {"guess": "Nope", "valid": False, "same_as": "", "new_name": ""},
    ]}]})  # fmt: skip
    accepted = review.judge(uow, writer, "m", None)
    assert accepted == [
        ("colleges", "Woody C", "Woodsworth College", None),
        ("colleges", "Massey", None, "Massey College"),
    ]
    # Half-typed fragments never reach the model.
    assert '"sh"' not in writer.requests[0]


def test_judge_skips_the_model_when_nothing_was_rejected():
    writer = _Writer({"prompts": []})
    assert review.judge(_Uow([PROMPTS_BY_ID["colleges"]], []), writer, "m", None) == []
    assert writer.requests == []
