"""Builders for generated prompt sets, shared by unit and integration tests."""

from rarest_blue.application import generation
from rarest_blue.domain import rules


def gen_prompt(
    pid: str, n: int = generation.MIN_ANSWERS + 2, golden_at: int = -2, category: str = "places", kind: str = "closed"
) -> generation.GenPrompt:
    answers = [generation.GenAnswer(name=f"Answer {pid} {i}", aliases=[f"alias {pid} {i}"], why="") for i in range(n)]
    return generation.GenPrompt(
        id=pid,
        category=category,
        kind=kind,
        set_size=0,
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


def addition(name: str, aliases: tuple[str, ...] = ()) -> generation.GenAnswer:
    return generation.GenAnswer(name=name, aliases=list(aliases), why="It's real.")


def verdict(
    gen: generation.GenPrompt,
    invalid: tuple[str, ...] = (),
    defensible: tuple[str, ...] = (),
    missing: tuple[generation.GenAnswer, ...] = (),
    **kw,
) -> generation.Verdict:
    """A verdict that checks every answer and decoy of `gen`: valid and wrong, except the ones named."""
    return generation.Verdict(
        **{
            "id": gen.id,
            "kind": gen.kind,
            "answers": [
                generation.AnswerCheck(name=a.name, valid=a.name not in invalid, more_aliases=[]) for a in gen.answers
            ],
            "decoys": [generation.DecoyCheck(decoy=d, defensible=d in defensible) for d in gen.decoys],
            "missing_answers": list(missing),
            "ambiguous": False,
            "problem": "",
            **kw,
        }
    )


def all_clear(gen: generation.GenSet) -> generation.Verdicts:
    return generation.Verdicts(prompts=[verdict(p) for p in gen.prompts])


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
