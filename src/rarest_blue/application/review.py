"""Use case: review rejected guesses and accept real answers the list missed, rescoring everyone they affect."""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date

from pydantic import BaseModel

from ..domain import scoring
from ..domain.matching import match_answer, normalize
from ..domain.models import Prompt
from .generation import _strict, parse_reply
from .ports import PromptWriter, UnitOfWork

log = logging.getLogger(__name__)

# Guesses shorter than this are almost always half-typed ("sha", "m"), so the judge never sees them.
MIN_JUDGED_CHARS = 3
JUDGE_TEMPERATURE = 0.0


def rejected(uow: UnitOfWork, day: date, limit: int) -> dict[str, list[tuple[str, int]]]:
    """Most common rejected guesses per prompt, as (example spelling, count)."""
    counts: dict[str, Counter] = defaultdict(Counter)
    spelling: dict[str, str] = {}
    for prompt_id, raw in uow.guesses.rejected(day):
        key = normalize(raw)
        if key:
            counts[prompt_id][key] += 1
            spelling.setdefault(key, raw.strip())
    return {pid: [(spelling[k], n) for k, n in c.most_common(limit)] for pid, c in counts.items()}


def with_answer(prompt: Prompt, guess: str, as_answer: str | None) -> Prompt:
    """The prompt with `guess` accepted, as an alias of `as_answer` or as a new answer."""
    guess = guess.strip()
    answers = list(prompt.answers)
    if as_answer is not None:
        canon = match_answer(prompt, as_answer)
        if canon is None:
            raise ValueError(f"'{as_answer}' isn't an answer to {prompt.id}")
        current = match_answer(prompt, guess)
        if current not in (None, canon):
            raise ValueError(f"'{guess}' already counts as '{current}'")
        if current is None:
            answers = [names + (guess,) if names[0] == canon else names for names in answers]
    elif match_answer(prompt, guess) is None:
        answers.append((guess,))
    updated = replace(prompt, answers=answers)
    # A decoy that now scores would mislead the autocomplete.
    return replace(updated, decoys=[d for d in prompt.decoys if match_answer(updated, d) is None])


def accept(uow: UnitOfWork, day: date, prompt_id: str, guess: str, as_answer: str | None = None) -> int:
    """Accept a guess and rescore what it matches. Returns how many guesses were rescored."""
    prompt = next((p for p in uow.prompts.get(day) or [] if p.id == prompt_id), None)
    if prompt is None:
        raise ValueError(f"no prompt '{prompt_id}' on {day.isoformat()}")
    prompt = with_answer(prompt, guess, as_answer)
    uow.prompts.replace_prompt(day, prompt)

    fixed = {
        player_id: answer
        for player_id, raw in uow.guesses.unmatched(day, prompt_id)
        if (answer := match_answer(prompt, raw)) is not None
    }
    if not fixed:
        return 0
    for player_id, answer in fixed.items():
        uow.guesses.set_answer(day, prompt_id, player_id, answer)
    # Score with the counts after the fix, so the newly accepted answers aren't all "rare".
    counts = scoring.answer_counts(prompt, uow.guesses.tallies(day, prompt_id))
    total = sum(counts.values())
    for player_id, answer in fixed.items():
        share = counts[answer] / total
        uow.guesses.set_score(day, prompt_id, player_id, scoring.points_for(prompt, answer, counts), share)
    uow.finishes.recompute_scores(day, list(fixed))
    return len(fixed)


class Ruling(BaseModel):
    guess: str
    valid: bool
    # The existing answer this guess is another name or misspelling of, or "" for a new answer.
    same_as: str
    # For a new answer, its proper display name ("Smoke's Poutinerie" for "smokes"), so variants group together.
    new_name: str


class PromptRulings(BaseModel):
    id: str
    rulings: list[Ruling]


class Rulings(BaseModel):
    prompts: list[PromptRulings]


RULINGS_SCHEMA = _strict(Rulings.model_json_schema())

JUDGE_INSTRUCTIONS = """\
You review rejected guesses for UofT Krillion, a trivia game for University of Toronto students.
Players typed each guess below as an answer to the prompt, and the game's answer list was missing
it. A real answer that scores zero makes a player feel cheated, which is the worst thing that can
happen in this game. Your job is to rescue those players.

Read the prompt and its hint the way a tired student would. A guess is valid when a reasonable
student could defend it as an answer, even if it's not what the list writer had in mind:
- Valid: "Red Bull" or "Monster" for a drink to survive a 9am; "coffee" or "double shot espresso"
  for a coffee drink; "chicken katsu" or "skewers" for food truck food; "Smoke's" for a chain near
  campus; "Gradescope" for an app UofT students use; "Scarborough" for where UofT students live.
- Valid: a misspelling or short form of a valid answer ("harnord" for Harbord Street).
- Not valid: half-typed fragments ("sha", "starbu", "kensint"), a different kind of thing than the
  prompt asks (a café's name for a drink prompt), jokes, and clearly wrong facts.

For every guess, return:
- `guess`: copied exactly.
- `valid`: true or false, by the rules above.
- `same_as`: if the guess is another name, short form or misspelling of an answer in `answers`,
  that answer copied exactly ("coffee" is Drip Coffee). Otherwise "".
- `new_name`: if it's valid and `same_as` is "", the answer's proper display name, spelled
  correctly ("Smoke's Poutinerie" for "smoke" and "smoke's"). Give the same `new_name` to every
  guess that means the same thing. Otherwise "".
"""


def build_judge_request(prompts: list[Prompt], found: dict[str, list[tuple[str, int]]]) -> str:
    body = [
        {"id": p.id, "text": p.text, "hint": p.hint, "answers": [n[0] for n in p.answers],
         "rejected_guesses": [raw for raw, _ in found[p.id]]}
        for p in prompts if found.get(p.id)
    ]  # fmt: skip
    return "\n\n".join([
        JUDGE_INSTRUCTIONS,
        "Reply with only a JSON object matching this schema:",
        json.dumps(RULINGS_SCHEMA),
        "The prompts:",
        json.dumps({"prompts": body}, indent=1),
    ])  # fmt: skip


def judge(
    uow: UnitOfWork, writer: PromptWriter, model: str, day: date, limit: int = 40
) -> list[tuple[str, str, str | None, str | None]]:
    """Have an LLM pick out the rejected guesses that are real answers.

    Each is (prompt id, guess, the existing answer it's another name for, or the display name of a new answer).
    """
    prompts = uow.prompts.get(day) or []
    found = {
        pid: [(raw, n) for raw, n in guesses if len(normalize(raw)) >= MIN_JUDGED_CHARS]
        for pid, guesses in rejected(uow, day, limit).items()
    }
    if not any(found.values()):
        return []
    reply = writer.write(build_judge_request(prompts, found), model, RULINGS_SCHEMA, JUDGE_TEMPERATURE)
    by_id = {p.id: p for p in prompts}
    asked = {pid: {normalize(raw) for raw, _ in guesses} for pid, guesses in found.items()}
    accepted = []
    for group in parse_reply(reply, Rulings).prompts:
        prompt = by_id.get(group.id)
        for ruling in group.rulings:
            # Only act on guesses players actually typed, never on anything the model made up.
            if prompt is None or not ruling.valid or normalize(ruling.guess) not in asked.get(group.id, set()):
                continue
            same_as = ruling.same_as.strip() or None
            if same_as is not None and match_answer(prompt, same_as) is None:
                same_as = None
            new_name = None if same_as else (ruling.new_name.strip() or None)
            accepted.append((group.id, ruling.guess.strip(), same_as, new_name))
    return accepted


def auto_accept(
    uow: UnitOfWork, writer: PromptWriter, model: str, day: date, dry_run: bool = False
) -> list[tuple[str, str, str | None, int]]:
    """Judge the day's rejected guesses and accept the real ones. Returns (prompt, guess, as, rescored)."""
    done = []
    for prompt_id, guess, same_as, new_name in judge(uow, writer, model, day):
        target = same_as or new_name
        if dry_run:
            done.append((prompt_id, guess, target, 0))
            continue
        try:
            rescored = 0
            if new_name and normalize(new_name) != normalize(guess):
                # Add the proper name first (a no-op if an earlier variant added it), then the typo as its alias.
                rescored += accept(uow, day, prompt_id, new_name)
                rescored += accept(uow, day, prompt_id, guess, new_name)
            else:
                rescored += accept(uow, day, prompt_id, guess, same_as)
            done.append((prompt_id, guess, target, rescored))
        except ValueError as e:  # already counts as something else, or the prompt changed underneath us
            log.info("skipped %s / %s: %s", prompt_id, guess, e)
    return done
