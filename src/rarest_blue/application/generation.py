"""Use case: have an LLM write tomorrow's prompt set, check it hard, and store it.

The checks matter more than the model: enough answers, no colliding aliases, a real deep-cut golden answer, and
decoys that don't accidentally match a real answer. A bad set is retried with the next model.
"""

from __future__ import annotations

import enum
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date
from typing import Literal

from pydantic import BaseModel

from ..domain import rules
from ..domain.matching import match_answer, normalize
from ..domain.models import Prompt
from ..domain.prompt_bank import PROMPTS_BY_ID
from .ports import PromptWriter, UnitOfWorkFactory

log = logging.getLogger(__name__)

MIN_ANSWERS = 15
GOLDEN_MIN_INDEX = 3
# The golden answer must sit in the last part of the list, past this fraction of it.
GOLDEN_MIN_FRACTION = 2 / 3
# Every prompt must name UofT or one of its places, so nothing drifts into general trivia.
UOFT_ANCHORS = (
    "uoft", "u of t", "university of toronto", "st. george", "st george", "utm", "utsc", "mississauga",
    "scarborough", "varsity", "robarts", "hart house", "sid smith", "bahen", "con hall", "convocation hall",
    "skule", "arts & sci", "arts and sci", "first-year", "frosh", "college",
)  # fmt: skip
ATTEMPTS = 3
AVOID_RECENT_DAYS = 14
# Free models default to "name a building" over and over, so cap how many prompts share a category.
MAX_PER_CATEGORY = 2

Category = Literal["places", "people", "academics", "student_life", "sports_clubs", "toronto", "history_traditions"]


class GenAnswer(BaseModel):
    name: str
    aliases: list[str]


class GenPrompt(BaseModel):
    id: str
    category: Category
    text: str
    hint: str
    golden: str
    answers: list[GenAnswer]
    decoys: list[str]


class GenSet(BaseModel):
    prompts: list[GenPrompt]


def _strict(schema: dict) -> dict:
    """Mark every object closed, as strict JSON-schema mode requires."""
    for obj in [schema, *schema.get("$defs", {}).values()]:
        if obj.get("type") == "object":
            obj["additionalProperties"] = False
    return schema


RESPONSE_SCHEMA = _strict(GenSet.model_json_schema())

INSTRUCTIONS = f"""\
You write the daily prompt set for UofT Krillion, a trivia game for University of Toronto students.
Players get a prompt like "Name a St. George college" and type any valid answer. The fewer
players who give the same answer, the more points they score, so every prompt needs a
large, complete, factually accurate list of valid answers.

Write exactly {rules.PROMPTS_PER_DAY} prompts. Rules:
- Niche is the point. Every prompt must be something only a UofT student or alum would know:
  campuses, buildings, course codes, clubs, traditions, residences, campus food, alumni, profs,
  slang. No general Toronto, Canada or world trivia, and no broad categories anyone could answer
  ("Name a Canadian university", "Name a sport"). The prompt text must name UofT or a UofT place.
- Tag each prompt with a `category`; at most {MAX_PER_CATEGORY} prompts may share one.
  Buildings, residences and streets are all "places".
- Only use prompts with a closed, verifiable set of answers. Every answer must be real; never
  invent one. Prefer fewer answers over doubtful ones.
- Each prompt needs at least {MIN_ANSWERS} answers, ideally 20 or more, listed from most to
  least obvious. List order seeds starting popularity.
- Make the answer list complete. A real answer missing from it scores zero for the player who
  typed it, which is the worst thing that can happen in this game.
- `name` is the canonical display name. `aliases` are other spellings, abbreviations and
  nicknames students would actually type: short forms ("Sid Smith"), codes, old names.
  Aliases must not overlap between answers.
- `golden` is one hidden deep-cut answer copied exactly from a `name`, from the last third of
  the list: something real that almost nobody will think of.
- `hint` is one short, playful line nudging players away from the obvious answers.
- `id` is a short snake_case slug for the prompt.
- `decoys` are about as many WRONG answers as there are right ones: real, plausible things that
  don't fit the prompt (near-misses, other campuses, other cities). The game recognizes them as
  wrong guesses, so none of them may be a valid answer.
"""


def _examples() -> str:
    picks = [(PROMPTS_BY_ID["colleges"], "places"), (PROMPTS_BY_ID["alumni"], "people")]
    return json.dumps({"prompts": [{**p.to_dict(), "category": c} for p, c in picks]}, indent=1)


def build_request(avoid: list[str]) -> str:
    parts = [
        INSTRUCTIONS,
        "Reply with only a JSON object matching this schema:",
        json.dumps(RESPONSE_SCHEMA),
        "Two example prompts, showing format and tone:",
        _examples(),
    ]
    if avoid:
        parts += ["Recently used prompts. Don't repeat these or close variants:", "\n".join(f"- {t}" for t in avoid)]
    return "\n\n".join(parts)


def parse_reply(content: str) -> GenSet:
    # Some models wrap JSON in a code fence even when asked not to.
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", (content or "").strip())
    return GenSet.model_validate_json(content)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40]


def clean_prompt(gen: GenPrompt) -> Prompt:
    """Turn one generated prompt into a playable Prompt, dropping bad aliases.

    Raises ValueError if the prompt can't be salvaged.
    """
    text, hint = gen.text.strip(), gen.hint.strip()
    if not text or not hint:
        raise ValueError(f"{gen.id}: empty text or hint")

    taken: set[str] = set()
    answers: list[tuple[str, ...]] = []
    for ans in gen.answers:
        name = ans.name.strip()
        key = normalize(name)
        if not key or key in taken:
            continue
        names = [name]
        taken.add(key)
        for alias in ans.aliases:
            alias_key = normalize(alias)
            if alias_key and alias_key not in taken:
                names.append(alias.strip())
                taken.add(alias_key)
        answers.append(tuple(names))

    if len(answers) < MIN_ANSWERS:
        raise ValueError(f"{gen.id}: only {len(answers)} usable answers")

    canon = [names[0] for names in answers]
    golden = next((n for n in canon if normalize(n) == normalize(gen.golden)), None)
    if golden is None:
        raise ValueError(f"{gen.id}: golden '{gen.golden}' isn't an answer")
    if canon.index(golden) < max(GOLDEN_MIN_INDEX, int(len(canon) * GOLDEN_MIN_FRACTION)):
        raise ValueError(f"{gen.id}: golden '{golden}' is too obvious")
    if not any(a in text.lower() for a in UOFT_ANCHORS):
        raise ValueError(f"{gen.id}: '{text}' doesn't name UofT or a UofT place")

    prompt = Prompt(id=_slug(gen.id) or _slug(text), text=text, hint=hint, golden=golden, answers=answers)
    # A "decoy" that matches a real answer would score, so drop those.
    decoys: dict[str, str] = {}
    for decoy in gen.decoys:
        decoy, key = decoy.strip(), normalize(decoy)
        if key and key not in taken and key not in decoys and match_answer(prompt, decoy) is None:
            decoys[key] = decoy
    return replace(prompt, decoys=list(decoys.values()))


def clean_set(gen: GenSet) -> list[Prompt]:
    n_needed = rules.PROMPTS_PER_DAY
    if len(gen.prompts) < n_needed:
        raise ValueError(f"got {len(gen.prompts)} prompts, need {n_needed}")
    picked = gen.prompts[:n_needed]
    prompts = [clean_prompt(p) for p in picked]
    ids = [p.id for p in prompts]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate prompt ids: {ids}")
    category, n = Counter(p.category for p in picked).most_common(1)[0]
    if n > MAX_PER_CATEGORY:
        raise ValueError(f"{n} prompts are '{category}', max is {MAX_PER_CATEGORY}")
    return prompts


class GenerationFailed(RuntimeError):
    pass


class PromptSetGenerator:
    """Asks the writer for a set, cycling through models, until one passes every check."""

    def __init__(self, writer: PromptWriter, models: list[str], attempts: int = ATTEMPTS):
        if not models:
            raise ValueError("need at least one model")
        self._writer = writer
        self._models = models
        self._attempts = attempts

    def generate(self, day: date, avoid: list[str]) -> tuple[list[Prompt], str]:
        """Returns the cleaned set and the model that wrote it."""
        request = build_request(avoid)
        last: Exception | None = None
        for attempt in range(1, self._attempts + 1):
            model = self._models[(attempt - 1) % len(self._models)].strip()
            try:
                return clean_set(parse_reply(self._writer.write(request, model, RESPONSE_SCHEMA))), model
            except Exception as e:  # API errors and validation failures both get another try
                log.warning("attempt %d/%d (%s) failed: %s", attempt, self._attempts, model, e)
                last = e
        raise GenerationFailed(f"no valid set for {day} after {self._attempts} attempts") from last


class Outcome(enum.Enum):
    STORED = enum.auto()
    SKIPPED = enum.auto()  # the day already had a set, so nothing was generated
    ALREADY_HAD_SET = enum.auto()  # another run stored a set while this one was generating
    DRY_RUN = enum.auto()


@dataclass(frozen=True)
class NightlyResult:
    outcome: Outcome
    day: date
    prompts: list[Prompt]


def run_nightly(
    uow: UnitOfWorkFactory, generator: PromptSetGenerator, day: date, dry_run: bool = False
) -> NightlyResult:
    """Generate and store `day`'s set unless it already has one. Raises GenerationFailed if no set passes."""
    with uow() as tx:
        if not dry_run and tx.prompts.get(day) is not None:
            return NightlyResult(Outcome.SKIPPED, day, [])
        avoid = tx.prompts.recent_texts(day, AVOID_RECENT_DAYS)

    # The LLM call can take minutes, so it runs outside any transaction.
    prompts, model = generator.generate(day, avoid)
    if dry_run:
        return NightlyResult(Outcome.DRY_RUN, day, prompts)
    with uow() as tx:
        stored = tx.prompts.add(day, prompts, source=model)
    return NightlyResult(Outcome.STORED if stored else Outcome.ALREADY_HAD_SET, day, prompts)
