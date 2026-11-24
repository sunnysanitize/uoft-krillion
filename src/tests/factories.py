"""Builders for generated prompt sets, shared by unit and integration tests."""

from rarest_blue.application import generation
from rarest_blue.domain import rules


def gen_prompt(
    pid: str, n: int = generation.MIN_ANSWERS + 2, golden_at: int = -2, category: str = "places"
) -> generation.GenPrompt:
    answers = [generation.GenAnswer(name=f"Answer {pid} {i}", aliases=[f"alias {pid} {i}"]) for i in range(n)]
    return generation.GenPrompt(
        id=pid,
        category=category,
        text=f"Name a UofT {pid}",
        hint="Go deep.",
        golden=answers[golden_at].name,
        answers=answers,
        decoys=[f"Wrong {pid} {i}" for i in range(3)],
    )


def gen_set() -> generation.GenSet:
    categories = list(generation.Category.__args__)
    return generation.GenSet(
        prompts=[
            gen_prompt(f"topic{i}", category=categories[i % len(categories)]) for i in range(rules.PROMPTS_PER_DAY)
        ]
    )


class FakeWriter:
    """A PromptWriter that replays canned replies (or raises) and records which models were asked."""

    def __init__(self, reply=None, error: Exception | None = None):
        self.reply, self.error, self.models = reply, error, []

    def write(self, request: str, model: str, response_schema: dict) -> str:
        self.models.append(model)
        if self.error:
            raise self.error
        return (self.reply or gen_set()).model_dump_json()
