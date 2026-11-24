"""Builders for generated prompt sets, shared by unit and integration tests."""

from rarest_blue.application import generation
from rarest_blue.domain import rules


def gen_prompt(
    pid: str, n: int = generation.MIN_ANSWERS + 2, golden_at: int = -2, category: str = "places"
) -> generation.GenPrompt:
    answers = [generation.GenAnswer(name=f"Answer {pid} {i}", aliases=[f"alias {pid} {i}"], why="") for i in range(n)]
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


def verdict(pid: str, **kw) -> generation.Verdict:
    return generation.Verdict(
        **{
            "id": pid,
            "ambiguous": False,
            "problem": "",
            "wrong_answers": [],
            "right_decoys": [],
            "missing_answers": [],
            **kw,
        }
    )


def all_clear(gen: generation.GenSet) -> generation.Verdicts:
    return generation.Verdicts(prompts=[verdict(p.id) for p in gen.prompts])


class FakeWriter:
    """A PromptWriter that replays canned replies (or raises) and records which models were asked.

    Generator requests get `reply` (default: a full set); verifier requests get `verdicts` (default: all clear).
    """

    def __init__(self, reply=None, verdicts=None, error: Exception | None = None):
        self.reply, self.verdicts, self.error, self.models = reply, verdicts, error, []

    def write(self, request: str, model: str, response_schema: dict, temperature: float) -> str:
        self.models.append(model)
        if self.error:
            raise self.error
        gen = self.reply or gen_set()
        if response_schema is generation.VERDICT_SCHEMA:
            return (self.verdicts or all_clear(gen)).model_dump_json()
        return gen.model_dump_json()
