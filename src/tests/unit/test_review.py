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
