"""Use case: check hand edits to a prompt set, whole files or one reviewer change at a time, before they're stored.

Errors would break the day (a golden answer that can't be scored, two answers sharing an alias, a decoy that
scores). Warnings are the generator's quality bars, which a human may knowingly relax.

Once a day is being played, only new answers and aliases can go in, through review.accept so the players who typed
them are rescored. Anything else would change scores players already have.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import date
from typing import Literal

from ..domain import rules
from ..domain.matching import match_answer, normalize
from ..domain.models import Prompt
from . import review
from .generation import GOLDEN_MIN_FRACTION, GOLDEN_MIN_INDEX, MIN_ANSWERS, UOFT_ANCHORS
from .ports import UnitOfWork

ChangeKind = Literal["add_answer", "add_alias", "remove_answer", "remove_decoy", "set_golden"]
# The only changes that can't take points away from anyone, so the only ones allowed once a day is being played.
LIVE_KINDS = {"add_answer", "add_alias"}


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


@dataclass(frozen=True)
class Change:
    """One reviewer edit to a stored prompt.

    `name` is the answer (or decoy) acted on. `text` is the new alias for add_alias and the explanation for
    set_golden; `aliases` go with a new answer.
    """

    kind: ChangeKind
    prompt_id: str
    name: str
    text: str = ""
    aliases: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v} | {"aliases": list(self.aliases)}

    @classmethod
    def from_dict(cls, data: dict) -> Change:
        return cls(
            kind=data["kind"],
            prompt_id=data["prompt_id"],
            name=data["name"],
            text=data.get("text", ""),
            aliases=tuple(data.get("aliases", ())),
        )


def apply_change(prompt: Prompt, change: Change) -> Prompt:
    """The prompt with the change made. Raises ValueError if it doesn't make sense for this prompt."""
    name = change.name.strip()
    if change.kind == "add_answer":
        names = (name, *(a.strip() for a in change.aliases if a.strip()))
        for n in names:
            if (hit := match_answer(prompt, n)) is not None:
                raise ValueError(f"'{n}' already counts as '{hit}'")
        # Just before the golden one, like the generator's additions, so the golden stays the deep cut.
        at = prompt.canonical_answers.index(prompt.golden) if prompt.golden in prompt.canonical_answers else None
        answers = list(prompt.answers)
        answers.insert(len(answers) if at is None else at, names)
        return _without_scoring_decoys(replace(prompt, answers=answers))

    if change.kind == "remove_decoy":
        kept = [d for d in prompt.decoys if normalize(d) != normalize(name)]
        if len(kept) == len(prompt.decoys):
            raise ValueError(f"'{name}' isn't a decoy of {prompt.id}")
        return replace(prompt, decoys=kept)

    canon = _answer(prompt, name)
    if change.kind == "add_alias":
        alias = change.text.strip()
        if (hit := match_answer(prompt, alias)) is not None:
            raise ValueError(f"'{alias}' already counts as '{hit}'")
        answers = [(*names, alias) if names[0] == canon else names for names in prompt.answers]
        return _without_scoring_decoys(replace(prompt, answers=answers))
    if change.kind == "remove_answer":
        if canon == prompt.golden:
            raise ValueError(f"'{canon}' is the golden answer; pick a new golden first")
        return replace(prompt, answers=[names for names in prompt.answers if names[0] != canon])
    if change.kind == "set_golden":
        # A new golden needs its own explanation; the old one was about a different answer.
        why = change.text.strip() or (prompt.golden_why if canon == prompt.golden else "")
        return replace(prompt, golden=canon, golden_why=why)
    raise ValueError(f"unknown change '{change.kind}'")


def is_live(uow: UnitOfWork, day: date, today: date) -> bool:
    """Being played: today or earlier, or already guessed on (a clock skew shouldn't let answers change under it)."""
    return day <= today or any(s.players for s in uow.guesses.stats(day).values())


def preview_change(uow: UnitOfWork, day: date, today: date, change: Change) -> tuple[Prompt, Report]:
    """What the prompt would become and the day's check report. Raises ValueError if the change can't be made."""
    prompts = uow.prompts.get(day)
    if prompts is None:
        raise ValueError(f"{day.isoformat()} has no stored set yet")
    prompt = next((p for p in prompts if p.id == change.prompt_id), None)
    if prompt is None:
        raise ValueError(f"{day.isoformat()} has no prompt '{change.prompt_id}'")
    if change.kind not in LIVE_KINDS and is_live(uow, day, today):
        raise ValueError(f"{day.isoformat()} is already being played, so only new answers and aliases can go in")
    updated = apply_change(prompt, change)
    return updated, check_set([updated if p.id == prompt.id else p for p in prompts])


def commit_change(uow: UnitOfWork, day: date, today: date, change: Change) -> int:
    """Check and store the change. Returns how many guesses were rescored (always 0 before the day goes live)."""
    updated, report = preview_change(uow, day, today, change)
    if not report.ok:
        raise ValueError("; ".join(report.errors))
    if not is_live(uow, day, today):
        uow.prompts.replace_prompt(day, updated)
        return 0
    if change.kind == "add_alias":
        return review.accept(uow, day, change.prompt_id, change.text, change.name)
    n = review.accept(uow, day, change.prompt_id, change.name)
    return n + sum(review.accept(uow, day, change.prompt_id, a, change.name) for a in change.aliases if a.strip())


def _answer(prompt: Prompt, name: str) -> str:
    canon = match_answer(prompt, name, fuzzy=False)
    if canon is None:
        raise ValueError(f"'{name}' isn't an answer to {prompt.id}")
    return canon


def _without_scoring_decoys(prompt: Prompt) -> Prompt:
    # A decoy that now scores would mislead the autocomplete.
    return replace(prompt, decoys=[d for d in prompt.decoys if match_answer(prompt, d) is None])
