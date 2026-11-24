"""Use case: check a hand-edited prompt set before it replaces a stored one.

Errors would break the day (a golden answer that can't be scored, two answers sharing an alias, a decoy that
scores). Warnings are the generator's quality bars, which a human may knowingly relax.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import rules
from ..domain.matching import match_answer, normalize
from ..domain.models import Prompt
from .generation import GOLDEN_MIN_FRACTION, GOLDEN_MIN_INDEX, MIN_ANSWERS, UOFT_ANCHORS


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def parse_set(data: object) -> tuple[list[Prompt], Report]:
    """Turn edited JSON (a list of prompt objects) into Prompts, reporting anything malformed."""
    report = Report()
    if not isinstance(data, list):
        report.errors.append("the file must be a JSON list of prompts")
        return [], report
    prompts = []
    for i, item in enumerate(data):
        try:
            prompt = Prompt.from_dict(item)
        except (KeyError, TypeError) as e:
            report.errors.append(f"prompt #{i + 1}: missing or malformed field {e}")
            continue
        if not all(isinstance(n, str) for names in prompt.answers for n in names) or not all(
            isinstance(d, str) for d in prompt.decoys
        ):
            report.errors.append(f"{prompt.id}: answers and decoys must be strings")
            continue
        prompts.append(prompt)
    return prompts, report


def check_set(prompts: list[Prompt], report: Report | None = None) -> Report:
    report = report or Report()
    if len(prompts) != rules.PROMPTS_PER_DAY:
        report.errors.append(f"need exactly {rules.PROMPTS_PER_DAY} prompts, found {len(prompts)}")
    ids = [p.id for p in prompts]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        report.errors.append(f"prompt id '{dup}' is used twice")
    for p in prompts:
        _check_prompt(p, report)
    return report


def _check_prompt(p: Prompt, report: Report) -> None:
    err, warn = report.errors.append, report.warnings.append
    if not p.id.strip() or not p.text.strip() or not p.hint.strip():
        err(f"{p.id or '?'}: id, text and hint must be non-empty")
    if not p.answers or any(not names or not names[0].strip() for names in p.answers):
        err(f"{p.id}: every answer needs a non-empty name")
        return

    owner: dict[str, str] = {}
    for names in p.answers:
        for name in names:
            key = normalize(name)
            if not key:
                err(f"{p.id}: '{name}' has no letters or digits, so it can never match")
            elif owner.setdefault(key, names[0]) != names[0]:
                err(f"{p.id}: '{name}' belongs to both '{owner[key]}' and '{names[0]}'")

    canon = p.canonical_answers
    if p.golden not in canon:
        err(f"{p.id}: golden '{p.golden}' must be copied exactly from an answer's first name")
    elif canon.index(p.golden) < max(GOLDEN_MIN_INDEX, int(len(canon) * GOLDEN_MIN_FRACTION)):
        warn(f"{p.id}: golden '{p.golden}' is early in the list, so it may be too obvious")

    for decoy in p.decoys:
        hit = match_answer(p, decoy)
        if hit is not None:
            err(f"{p.id}: decoy '{decoy}' would score as '{hit}'; remove it or fix the answer")

    if len(canon) < MIN_ANSWERS:
        warn(f"{p.id}: only {len(canon)} answers (the generator wants {MIN_ANSWERS}+); missing answers score zero")
    if not any(a in p.text.lower() for a in UOFT_ANCHORS):
        warn(f"{p.id}: the text doesn't name UofT or a UofT place")
