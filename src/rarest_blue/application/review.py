"""Use case: review rejected guesses and accept real answers the list missed, rescoring everyone they affect."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date

from ..domain import scoring
from ..domain.matching import match_answer, normalize
from ..domain.models import Prompt
from .ports import UnitOfWork


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
