"""Use case: have an LLM write tomorrow's prompt set, fact-check it with a second LLM, check it hard, and store it.

The generator over-writes candidates. The verifier, from a different model family, drops ambiguous prompts and wrong
answers. Then the code checks what's left: enough answers, no colliding aliases, a real deep-cut golden answer,
decoys that don't accidentally match a real answer, and nothing that reruns a recent prompt.
"""

from __future__ import annotations

import enum
import json
import logging
import random
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

# Ask for more prompts than a day needs, so the verifier and the repeat check can throw some away.
CANDIDATES = 12
MIN_ANSWERS = 15
# What the generator is asked for: enough headroom that the verifier can cut a few and stay above MIN_ANSWERS.
TARGET_ANSWERS = 20
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
AVOID_RECENT_DAYS = 60
# A candidate sharing this much of its answer list with a recent prompt is a rerun, however it's worded.
MAX_ANSWER_OVERLAP = 0.5
# Models default to "name a building" over and over, so cap how many prompts share a category.
MAX_PER_CATEGORY = 2
# Some variety for the writer; the checker should be as consistent as it can be.
GENERATOR_TEMPERATURE = 1.0
VERIFIER_TEMPERATURE = 0.0

Category = Literal["places", "people", "academics", "student_life", "sports_clubs", "toronto", "history_traditions"]


class GenAnswer(BaseModel):
    name: str
    aliases: list[str]
    why: str


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


class Verdict(BaseModel):
    id: str
    ambiguous: bool
    problem: str
    wrong_answers: list[str]
    right_decoys: list[str]


class Verdicts(BaseModel):
    prompts: list[Verdict]


def _strict(schema: dict) -> dict:
    """Mark every object closed, as strict JSON-schema mode requires."""
    for obj in [schema, *schema.get("$defs", {}).values()]:
        if obj.get("type") == "object":
            obj["additionalProperties"] = False
    return schema


RESPONSE_SCHEMA = _strict(GenSet.model_json_schema())
VERDICT_SCHEMA = _strict(Verdicts.model_json_schema())

INSTRUCTIONS = f"""\
You write the daily prompt set for UofT Krillion, a trivia game for University of Toronto students.
Players get a prompt like "Name a St. George college" and type any valid answer. The fewer
players who give the same answer, the more points they score, so every prompt needs a
large, complete, factually accurate list of valid answers.

Write exactly {CANDIDATES} prompts. Rules:
- Niche is the point. Every prompt must be something only a UofT student or alum would know:
  campuses, buildings, course codes, clubs, traditions, residences, campus food, alumni, profs,
  slang. No general Toronto, Canada or world trivia, and no broad categories anyone could answer
  ("Name a Canadian university", "Name a sport"). The prompt text must name UofT or a UofT place.
- Tag each prompt with a `category`; at most {MAX_PER_CATEGORY} prompts may share one.
  Buildings, residences and streets are all "places".
- Only use prompts with a closed, verifiable set of answers. Every answer must be real; never
  invent one. Prefer fewer answers over doubtful ones.
- Each prompt needs at least {TARGET_ANSWERS} answers, listed from most to least obvious. List
  order seeds starting popularity. A fact checker removes doubtful answers and any prompt left
  under {MIN_ANSWERS} is thrown out, so only pick prompts with a large, closed set of answers.
- Make the answer list complete. A real answer missing from it scores zero for the player who
  typed it, which is the worst thing that can happen in this game.
- `name` is the canonical display name. `aliases` are other spellings, abbreviations and
  nicknames students would actually type: short forms ("Sid Smith"), codes, old names.
  Aliases must not overlap between answers.
- `why` is one short factual line saying why the answer is valid ("Opened in 1973 on St. George
  St."). A fact checker reads it, so make it specific and true.
- `golden` is one hidden deep-cut answer copied exactly from a `name`, from the last third of
  the list: something real that almost nobody will think of.
- `hint` is one short, playful line nudging players away from the obvious answers.
- `id` is a short snake_case slug for the prompt.
- `decoys` are about as many WRONG answers as there are right ones: real, plausible things that
  don't fit the prompt (near-misses, other campuses, other cities). The game recognizes them as
  wrong guesses, so none of them may be a valid answer.
"""


VERIFY_INSTRUCTIONS = """\
You are the fact checker for UofT Krillion, a trivia game for University of Toronto students.
Players answer each prompt below by typing any valid answer. A wrong answer in the list lets
players score with something false; a right answer listed as a decoy scores zero for the player
who typed it. Check every prompt independently and judge it on facts, not on the `why` lines.

For each prompt, return:
- `id`: copied from the prompt.
- `ambiguous`: true if the prompt has no clear, closed set of answers, or reasonable UofT
  students would disagree about what counts.
- `problem`: one line explaining why it's ambiguous, or "" if it isn't.
- `wrong_answers`: from the `answers` list only, the `name` of every answer that isn't real,
  doesn't fit the prompt, or has an alias that points at something else. Copy names exactly.
- `right_decoys`: from `decoys_meant_to_be_wrong`, every decoy that actually is a valid answer.
  Copy them exactly. Decoys are supposed to be wrong, so never list one in `wrong_answers`.

Only flag what you're confident about. Leave the lists empty when everything checks out.
"""


def _examples() -> str:
    # Examples must meet the same answer-count contract as generated candidates.
    picks = [(PROMPTS_BY_ID["utm_departments"], "academics"), (PROMPTS_BY_ID["hart_house_clubs"], "sports_clubs")]
    examples = []
    for prompt, category in picks:
        example = {**prompt.to_dict(), "category": category}
        example["answers"] = [{"name": names[0], "aliases": list(names[1:]), "why": "..."} for names in prompt.answers]
        examples.append(example)
    return json.dumps({"prompts": examples}, indent=1)


def focus(day: date) -> list[str]:
    """Two categories to lean on, picked from the date so each day starts somewhere different."""
    categories = list(Category.__args__)
    random.Random(day.toordinal()).shuffle(categories)  # noqa: S311 - variety, not security
    return categories[:2]


def build_request(day: date, recent: list[Prompt]) -> str:
    lean = focus(day)
    parts = [
        INSTRUCTIONS,
        f"Today, lean toward the '{lean[0]}' and '{lean[1]}' categories.",
        "Reply with only a JSON object matching this schema:",
        json.dumps(RESPONSE_SCHEMA),
        "Two example prompts, showing format and tone:",
        _examples(),
    ]
    avoid = list(dict.fromkeys(p.text for p in recent))
    if avoid:
        parts += [
            "Prompts used recently. Don't repeat these, reword them, or ask for the same set of answers:",
            "\n".join(f"- {t}" for t in avoid),
        ]
    return "\n\n".join(parts)


def build_verify_request(gen: GenSet) -> str:
    prompts = [
        {
            "id": p.id,
            "text": p.text,
            "answers": [a.model_dump() for a in p.answers],
            "decoys_meant_to_be_wrong": p.decoys,
        }
        for p in gen.prompts
    ]
    return "\n\n".join([
        VERIFY_INSTRUCTIONS,
        "Reply with only a JSON object matching this schema:",
        json.dumps(VERDICT_SCHEMA),
        "The prompts:",
        json.dumps({"prompts": prompts}, indent=1),
    ])  # fmt: skip


def parse_reply[T: BaseModel](content: str, schema: type[T] = GenSet) -> T:
    # Some models wrap JSON in a code fence even when asked not to.
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", (content or "").strip())
    return schema.model_validate_json(content)


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
        # Models sometimes pick a mid-list golden; the deepest answer is a fine stand-in.
        log.info("%s: golden '%s' is too obvious, using '%s'", gen.id, golden, canon[-1])
        golden = canon[-1]
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


def apply_verdict(gen: GenPrompt, verdict: Verdict) -> GenPrompt:
    """Drop the answers the verifier says are wrong and promote decoys it says are right.

    A wrong golden answer hands the bonus to the deepest answer left. Raises ValueError if the prompt is ambiguous.
    """
    if verdict.ambiguous:
        raise ValueError(f"{gen.id}: ambiguous ({verdict.problem})")
    wrong = {normalize(n) for n in verdict.wrong_answers}
    right = {normalize(d) for d in verdict.right_decoys}
    answers = [a for a in gen.answers if normalize(a.name) not in wrong]
    if len(answers) < len(gen.answers):
        log.info("%s: verifier dropped %d answers", gen.id, len(gen.answers) - len(answers))
    golden = gen.golden
    if normalize(golden) in wrong and answers:
        golden = answers[-1].name
        log.info("%s: golden '%s' is wrong, using '%s'", gen.id, gen.golden, golden)
    # A real answer missing from the list scores zero, so a right "decoy" becomes a (rare) answer.
    answers += [GenAnswer(name=d, aliases=[], why="") for d in gen.decoys if normalize(d) in right]
    decoys = [d for d in gen.decoys if normalize(d) not in right]
    return gen.model_copy(update={"answers": answers, "decoys": decoys, "golden": golden})


def check_candidates(gen: GenSet, verdicts: Verdicts) -> list[tuple[str, Prompt]]:
    """Verified, cleaned candidates with their categories. Ones that fail are skipped, not fatal."""
    by_id = {v.id: v for v in verdicts.prompts}
    checked = []
    for candidate in gen.prompts:
        try:
            if candidate.id not in by_id:
                raise ValueError(f"{candidate.id}: the verifier didn't judge it")
            checked.append((candidate.category, clean_prompt(apply_verdict(candidate, by_id[candidate.id]))))
        except ValueError as e:
            log.info("dropped %s", e)
    return checked


def answer_overlap(a: Prompt, b: Prompt) -> float:
    """Share of the smaller answer list that the other list also has."""
    names_a = {normalize(names[0]) for names in a.answers}
    names_b = {normalize(names[0]) for names in b.answers}
    return len(names_a & names_b) / max(1, min(len(names_a), len(names_b)))


def pick_set(candidates: list[tuple[str, Prompt]], recent: list[Prompt]) -> list[Prompt]:
    """The first full day's worth of candidates that are new and spread across categories."""
    n_needed = rules.PROMPTS_PER_DAY
    picked: list[Prompt] = []
    per_category: Counter[str] = Counter()
    for category, prompt in candidates:
        if any(prompt.id == p.id or answer_overlap(prompt, p) >= MAX_ANSWER_OVERLAP for p in recent + picked):
            log.info("dropped %s: repeats a recent or picked prompt", prompt.id)
            continue
        if per_category[category] >= MAX_PER_CATEGORY:
            continue
        picked.append(prompt)
        per_category[category] += 1
        if len(picked) == n_needed:
            return picked
    raise ValueError(f"only {len(picked)} usable prompts, need {n_needed}")


class GenerationFailed(RuntimeError):
    pass


class PromptSetGenerator:
    """Has one model write candidates and another fact-check them, until a full set passes every check."""

    def __init__(self, writer: PromptWriter, generator_model: str, verifier_model: str, attempts: int = ATTEMPTS):
        self._writer = writer
        self._generator_model = generator_model
        self._verifier_model = verifier_model
        self._attempts = attempts

    def generate(self, day: date, recent: list[Prompt]) -> tuple[list[Prompt], str]:
        """Returns the verified set and the models that wrote and checked it."""
        request = build_request(day, recent)
        last: Exception | None = None
        for attempt in range(1, self._attempts + 1):
            try:
                reply = self._writer.write(request, self._generator_model, RESPONSE_SCHEMA, GENERATOR_TEMPERATURE)
                gen = parse_reply(reply)
                reply = self._writer.write(
                    build_verify_request(gen), self._verifier_model, VERDICT_SCHEMA, VERIFIER_TEMPERATURE
                )
                verdicts = parse_reply(reply, Verdicts)
                source = f"{self._generator_model} + {self._verifier_model}"
                return pick_set(check_candidates(gen, verdicts), recent), source
            except Exception as e:  # API errors and validation failures both get another try
                log.warning("attempt %d/%d failed: %s", attempt, self._attempts, e)
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
        recent = tx.prompts.recent(day, AVOID_RECENT_DAYS)

    # The LLM calls can take minutes, so they run outside any transaction.
    prompts, model = generator.generate(day, recent)
    if dry_run:
        return NightlyResult(Outcome.DRY_RUN, day, prompts)
    with uow() as tx:
        stored = tx.prompts.add(day, prompts, source=model)
    return NightlyResult(Outcome.STORED if stored else Outcome.ALREADY_HAD_SET, day, prompts)
