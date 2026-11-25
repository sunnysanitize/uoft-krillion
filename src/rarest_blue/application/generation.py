"""Use case: have an LLM write tomorrow's prompt set, fact-check it with a second LLM, check it hard, and store it.

The generator over-writes candidates. The verifier, from a different model family, checks each prompt on its own with
web search: it finds the official list, judges every answer and every decoy one by one, and adds the answers the writer
missed. Then the code checks what's left: enough answers for how open the
prompt is, no colliding aliases, a real deep-cut golden answer, decoys that don't overlap a real answer, and nothing
that reruns a recent prompt.
"""

from __future__ import annotations

import enum
import json
import logging
import random
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import date
from typing import Literal

from pydantic import BaseModel

from ..domain import rules
from ..domain.matching import MIN_PREFIX_CHARS, match_answer, normalize
from ..domain.models import Prompt
from ..domain.prompt_bank import PROMPTS_BY_ID
from .ports import PromptWriter, UnitOfWorkFactory

log = logging.getLogger(__name__)

# Ask for more prompts than a day needs, so the verifier and the repeat check can throw some away.
CANDIDATES = 15
# Specific sets ("a room in Myhal") are welcome, since broad ones run out; what a closed prompt can't be is incomplete.
MIN_ANSWERS = rules.MIN_ACCEPTED_ANSWERS
# The writer is told to pick sets at least this big, with headroom for the verifier's cuts above MIN_ANSWERS.
MIN_SET_SIZE = 20
# Open prompts ("a food from a food truck") have no fixed list, so players type far more than any list holds.
OPEN_MIN_ANSWERS = 30
OPEN_TARGET_ANSWERS = 45
# The verifier's additions go into the game unchecked. On a closed set they must come from the sources it searched (from
# memory they were how wrong answers got in, "presidents" who led other universities). Filling gaps from a source is
# the point, so this is generous; more than this and the writer was listing some other set.
MAX_CLOSED_ADDITIONS = 30
NAME_TITLES = frozenset({"the", "honourable", "hon", "sir", "dr", "rt", "right", "reverend", "rev"})
# Each prompt gets its own verifier request so it can search for that set; these run side by side.
VERIFY_WORKERS = 8
# A verdict that skips this much of the answer list didn't really check it.
MIN_JUDGED_SHARE = 0.8
GOLDEN_MIN_INDEX = 3
# The golden answer must sit in the last part of the list, past this fraction of it.
GOLDEN_MIN_FRACTION = 2 / 3
# Every prompt must name UofT or one of its places, so nothing drifts into general trivia.
UOFT_ANCHORS = (
    "uoft", "u of t", "university of toronto", "st. george", "st george", "utm", "utsc", "mississauga",
    "scarborough", "varsity", "robarts", "hart house", "sid smith", "bahen", "con hall", "convocation hall",
    "skule", "arts & sci", "arts and sci", "first-year", "frosh", "college", "myhal",
)  # fmt: skip
ATTEMPTS = 3
AVOID_RECENT_DAYS = 60
# A candidate sharing this much of its answer list with a recent prompt is a rerun, however it's worded.
MAX_ANSWER_OVERLAP = 0.3
# Models default to "name a building" over and over, so cap how many prompts share a category.
MAX_PER_CATEGORY = 2
# Some variety for the writer; the checker should be as consistent as it can be.
GENERATOR_TEMPERATURE = 1.0
VERIFIER_TEMPERATURE = 0.0

Category = Literal["places", "people", "academics", "student_life", "sports_clubs", "toronto", "history_traditions"]
# closed: a fixed, checkable set (colleges, presidents). open: everyday things with no list (foods, drinks, apps).
Kind = Literal["closed", "open"]


class GenAnswer(BaseModel):
    name: str
    aliases: list[str]
    why: str


class GenPrompt(BaseModel):
    id: str
    category: Category
    kind: Kind
    # How many members the full set has, per the writer; 0 for open prompts.
    set_size: int
    text: str
    hint: str
    golden: str
    answers: list[GenAnswer]
    decoys: list[str]


class GenSet(BaseModel):
    prompts: list[GenPrompt]


class AnswerCheck(BaseModel):
    name: str
    valid: bool
    more_aliases: list[str]


class DecoyCheck(BaseModel):
    decoy: str
    defensible: bool


class Verdict(BaseModel):
    # One check per answer and per decoy, so the verifier can't wave a list through by leaving it out.
    id: str
    kind: Kind
    answers: list[AnswerCheck]
    decoys: list[DecoyCheck]
    missing_answers: list[GenAnswer]
    # Every member of a closed set as its sources list it, so the code can diff it against the answers itself.
    source_members: list[str]
    # Where it checked the set. A closed prompt with none was only checked from memory.
    sources: list[str]
    # False when a player could type a real answer that's in neither the list nor missing_answers.
    complete: bool
    ambiguous: bool
    problem: str


class Verdicts(BaseModel):
    """Every prompt's verdict. Each comes from its own request, so this is assembled, never asked for."""

    prompts: list[Verdict]


def _strict(schema: dict) -> dict:
    """Mark every object closed, as strict JSON-schema mode requires."""
    for obj in [schema, *schema.get("$defs", {}).values()]:
        if obj.get("type") == "object":
            obj["additionalProperties"] = False
    return schema


RESPONSE_SCHEMA = _strict(GenSet.model_json_schema())
VERDICT_SCHEMA = _strict(Verdict.model_json_schema())

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
- Tag each prompt with a `kind`:
  - "closed": any prompt about specific facts: people, places, organizations, courses, events
    (colleges, presidents, UTM buildings, Arts & Science departments, famous alumni). Prefer
    these. List every member, not a sample, and set `set_size` to how many members the full set
    has; a list shorter than its set is thrown out. Every qualifier in the prompt binds
    every answer: a UTM prompt takes only UTM buildings, an Arts & Science prompt only its own
    departments (not separate faculties or schools), a president prompt only people who held
    that office at UofT.
  - "open": everyday things where anything of that type counts (foods, drinks, apps, chains).
    Set `set_size` to 0. These need at least {OPEN_TARGET_ANSWERS} answers, because players type
    whatever comes to mind: the plain everyday word ("coffee", "pizza"), every sub-type, cuisine
    and dish (a food prompt needs katsu, ramen, sushi and skewers as well as fries), every brand
    and the boring obvious ones. If you can't list {OPEN_TARGET_ANSWERS}, pick another prompt.
- Every answer must be real; never invent one. Closed prompts: completeness beats size. A
  specific set is good ("a room or space in Myhal", "a Hart House club", "a building on the UTM
  campus"), since broad ones run out, but only pick a set UofT publishes a list of (a building
  directory, a map legend, a department or residence page, a history of the office), worded
  with the same scope as that list, because the fact checker checks against it. No sets nobody
  lists ("streets around campus", "Skule traditions"). List every member a student could name,
  with old names and nicknames as aliases; if you aren't sure you know every member, pick
  another set. Never stop early: list all of them, however many that is (30 or 60 is normal),
  and never pad a small set with false answers. Only pick sets with at least {MIN_SET_SIZE}
  members: the seven colleges or six subway stations give players too little choice.
  {MIN_SET_SIZE} is a floor on the set, not a place to stop listing. Word the prompt plainly and
  exactly as wide as the set: "Name a UTSC building", not "a building or main structural wing on
  UTSC". List answers from most to least obvious; list order seeds starting popularity. A fact
  checker removes doubtful answers, throws out any list it finds incomplete, and any closed
  prompt left under {MIN_ANSWERS} (open: under {OPEN_MIN_ANSWERS}) is thrown out.
- A real answer missing from the list scores zero for the player who typed it, which is the
  worst thing that can happen in this game.
- The prompt text and hint set the scope players will answer. Word them exactly as narrowly as
  the list. Don't word a prompt broadly ("a drink to survive a 9am") and then only accept a
  narrow slice of it, and never let the hint invite answers the list doesn't have.
- `name` is the canonical display name. `aliases` are other spellings, abbreviations and
  nicknames students would actually type: short forms ("Sid Smith"), codes, old names, and the
  variants with an everyday modifier ("double espresso", "iced latte", "chicken katsu").
  Aliases must not overlap between answers.
- `why` is one short factual line saying why the answer is valid ("Opened in 1973 on St. George
  St."). A fact checker reads it, so make it specific and true.
- `golden` is one hidden deep-cut answer copied exactly from a `name`, from the last third of
  the list: something real that almost nobody will think of. Players see its `why` when the
  golden is revealed, so make that line the interesting fact about it.
- `hint` is one short, playful line nudging players away from the obvious answers.
- `id` is a short snake_case slug for the prompt.
- `decoys` are about as many WRONG answers as there are right ones: real things that clearly
  don't fit the prompt (other campuses, other cities, other categories). The game recognizes them
  as wrong guesses, so none of them may be a valid answer. Check each one: if the prompt asks for
  namesakes and a building bears that name, or a reasonable student could argue it fits the
  wording or hint (an energy drink for "a drink to survive a 9am"), it isn't a decoy: make it an
  answer or leave it out.
"""


VERIFY_INSTRUCTIONS = """\
You are the fact checker for UofT Krillion, a trivia game for University of Toronto students.
Players answer the prompt below by typing any valid answer. A wrong answer in the list lets
players score with something false; a real answer missing from it, or listed as a decoy, scores
zero and angers every player who typed it. Judge it on facts, not on the `why` lines.

Search the web first. For a closed prompt, find the official or most authoritative list of the
set (UofT's own pages first: utoronto.ca and its campus, faculty and college sites) and compare
the answers against it member by member. For an open prompt, search where it helps (which food
trucks park on St. George and what they serve). Don't rely on memory where a source can settle it.

Return:
- `id`: copied from the prompt.
- `kind`: "closed" if the answers are specific facts (people, places, organizations, courses:
  colleges, presidents, buildings, departments, alumni), even with no official list; "open" if
  they're everyday things where anything of that type counts (foods, drinks, apps, chains).
- `answers`: one entry for every item in `answers`, in order, none skipped. `name` copied
  exactly. `valid` is false if it isn't real, breaks any qualifier in the prompt (wrong campus,
  a separate faculty for a department prompt, someone who held the office elsewhere or held a
  different office), duplicates another answer, or has an alias that points at something else.
  A real member your sources just don't mention (an old name, a nickname, an unlisted room) is
  still valid: dropping a real answer is as bad as missing one.
  `more_aliases`: other ways students would type it that its aliases miss (short forms,
  misspellings, modifier variants like "double shot espresso"), or [].
- `decoys`: one entry for every item in `decoys_meant_to_be_wrong`, none skipped, `decoy`
  copied exactly. `defensible` is true if it's a valid answer given the prompt text and its
  hint. Closed prompts: true if it really belongs to the set (a real person a building is named
  after, when the prompt asks for namesakes). Open prompts: true if a reasonable UofT student
  could argue for it (an energy drink for a "survive a 9am" drink); when in doubt, true, since
  rejecting a defensible answer is worse than accepting one.
- `missing_answers`: real answers players are likely to type that aren't in the list under any
  name or alias, each with `aliases` and a specific, true `why`. These go into the game without
  another check.
  - Open prompts: be generous. Go through every sub-type (for apps: social, school, food,
    transit, banking) and add the everyday words and big brands first ("coffee", "ramen"), then
    rarer ones. Add as many as it takes.
  - Closed prompts: add every member your sources list that the answers miss, under its official
    name, with the nicknames students use as aliases and a `why` naming the source. Only add
    what a source shows: an answer from another campus, faculty or university is worse than a
    gap, because players are shown deep cuts as facts to learn.
- `source_members`: for a closed prompt, every member of the set exactly as your sources name
  it, all of them, whether or not the answers already have it; [] for an open prompt. Any the
  answers miss are added to the game.
- `sources`: for a closed prompt, the URLs of pages that list the set itself (a directory, a map
  legend, an official list), or [] if you only found scattered mentions of some members.
- `complete`: judged with your `missing_answers` added, since they fix the gaps you found. False
  only if a player could still type a real answer that's in neither (a building, room, street or
  truck your sources didn't settle, so you couldn't add it), or you couldn't find a source to
  check a closed list against.
- `ambiguous`: true if reasonable UofT students would disagree about what counts, or a closed
  prompt's wording or hint invites answers its set can't hold. For an open prompt that's worded
  more broadly than its list, add the missing answers instead.
- `problem`: one line explaining why it's ambiguous, or "" if it isn't.
"""


def _examples() -> str:
    # Examples must meet the same answer-count contract as generated candidates. The writer copies their length, so
    # they're the bank's broadest closed prompts, not ones sitting at the minimum.
    picks = [(PROMPTS_BY_ID["utsc_map_locations"], "places"), (PROMPTS_BY_ID["libraries"], "academics")]
    examples = []
    for prompt, category in picks:
        example = {**prompt.to_dict(), "category": category, "kind": "closed", "set_size": len(prompt.answers)}
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


def build_verify_request(p: GenPrompt) -> str:
    prompt = {
        "id": p.id,
        "text": p.text,
        # The hint sets scope as much as the text does, so decoys are judged against both.
        "hint": p.hint,
        "answers": [a.model_dump() for a in p.answers],
        "decoys_meant_to_be_wrong": p.decoys,
    }
    return "\n\n".join([
        VERIFY_INSTRUCTIONS,
        "Reply with only a JSON object matching this schema:",
        json.dumps(VERDICT_SCHEMA),
        "The prompt:",
        json.dumps(prompt, indent=1),
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

    needed = OPEN_MIN_ANSWERS if gen.kind == "open" else MIN_ANSWERS
    if len(answers) < needed:
        raise ValueError(f"{gen.id}: only {len(answers)} usable answers for a {gen.kind} prompt")

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

    golden_why = next((a.why.strip() for a in gen.answers if normalize(a.name) == normalize(golden)), "")
    prompt = Prompt(
        id=_slug(gen.id) or _slug(text), text=text, hint=hint, golden=golden, answers=answers, golden_why=golden_why
    )
    # A "decoy" that matches a real answer would score, so drop those. So do ones sharing a whole name with an
    # answer ("Milk" next to "steamed milk"): players can defend those, and a dropped decoy costs nothing.
    decoys: dict[str, str] = {}
    for decoy in gen.decoys:
        decoy, key = decoy.strip(), normalize(decoy)
        if not key or key in taken or key in decoys or match_answer(prompt, decoy) is not None:
            continue
        if not any(_contains(key, t) or _contains(t, key) for t in taken):
            decoys[key] = decoy
    return replace(prompt, decoys=list(decoys.values()))


def _contains(outer: str, inner: str) -> bool:
    """Is `inner` a distinctive run of whole words inside `outer`?"""
    return len(inner) >= MIN_PREFIX_CHARS and f" {inner} " in f" {outer} "


def apply_verdict(gen: GenPrompt, verdict: Verdict) -> GenPrompt:
    """Apply the verifier's per-item checks: drop wrong answers, promote defensible decoys, add what's missing.

    A wrong golden answer hands the bonus to the deepest answer left. Raises ValueError if the prompt is ambiguous or
    incomplete, the verdict skipped too much of the list, or a closed list's length doesn't match its set.
    """
    if verdict.ambiguous:
        raise ValueError(f"{gen.id}: ambiguous ({verdict.problem})")
    # A real answer missing from the list scores zero and angers every player who typed it, so an incomplete list
    # is thrown out rather than shipped.
    if not verdict.complete:
        raise ValueError(f"{gen.id}: the verifier says the list is incomplete")
    if "closed" in (gen.kind, verdict.kind) and not verdict.sources:
        raise ValueError(f"{gen.id}: the verifier found no source to check the set against")
    if gen.kind == "closed" and len(gen.answers) + len(verdict.missing_answers) < gen.set_size:
        raise ValueError(f"{gen.id}: {len(gen.answers)} answers for a set of {gen.set_size}, so it's a sample")
    checks = {normalize(c.name): c for c in verdict.answers}
    answers, judged, invalid = [], 0, set()
    for ans in gen.answers:
        keys = [normalize(n) for n in (ans.name, *ans.aliases)]
        check = next((checks[k] for k in keys if k in checks), None)
        if check is None:  # only the writer vouches for it, which is how every answer used to get in
            answers.append(ans)
            continue
        judged += 1
        if check.valid:
            answers.append(ans.model_copy(update={"aliases": [*ans.aliases, *check.more_aliases]}))
        else:
            invalid.update(keys)
    if judged < MIN_JUDGED_SHARE * len(gen.answers):
        raise ValueError(f"{gen.id}: the verifier only judged {judged} of {len(gen.answers)} answers")
    if len(answers) < len(gen.answers):
        log.info("%s: verifier dropped %d answers", gen.id, len(gen.answers) - len(answers))
    if gen.kind == verdict.kind == "closed" and 0 < gen.set_size < len(answers):
        raise ValueError(f"{gen.id}: {len(answers)} answers for a set of {gen.set_size}, so some are padding")

    # A real answer missing from the list scores zero, so a defensible "decoy" becomes an answer. Unjudged decoys go
    # too: a missing decoy only means one fewer name in the autocomplete.
    defensible = {normalize(c.decoy) for c in verdict.decoys if c.defensible}
    wrong = {normalize(c.decoy) for c in verdict.decoys if not c.defensible}
    promoted = [GenAnswer(name=d, aliases=[], why="") for d in gen.decoys if normalize(d) in defensible]
    decoys = [d for d in gen.decoys if normalize(d) in wrong]
    # Additions the verifier contradicts itself on (an answer it called wrong, a decoy it called wrong) stay out.
    added = [
        m
        for m in verdict.missing_answers
        if m.name.strip() and m.why.strip() and normalize(m.name) not in invalid | wrong
    ]
    # Asked to "add what's missing", the verifier leaves gaps; asked to list the set from its source, it gets it all. So
    # the code does the diff. A sourced answer nobody types costs nothing; a missing one angers everyone who typed it.
    if verdict.kind == "closed":
        added += _unlisted(verdict, [*answers, *promoted, *added], skip=invalid | wrong)
    if verdict.kind == "closed" and len(added) > MAX_CLOSED_ADDITIONS:
        raise ValueError(f"{gen.id}: the verifier found {len(added)} missing answers, so the list was a sample")

    golden = gen.golden
    if normalize(golden) in invalid and answers:
        golden = answers[-1].name
        log.info("%s: golden '%s' is wrong, using '%s'", gen.id, gen.golden, golden)
    # New answers go just before the golden one: past the obvious ones, and never pushing the golden out of the
    # deep end of the list (or replacing it with an unchecked addition).
    at = next((i for i, a in enumerate(answers) if normalize(a.name) == normalize(golden)), len(answers))
    answers[at:at] = [*promoted, *added]
    # Either model calling it open means players will type more than any list holds, so it needs the broad list.
    kind = "open" if "open" in (gen.kind, verdict.kind) else "closed"
    return gen.model_copy(update={"answers": answers, "decoys": decoys, "golden": golden, "kind": kind})


def _unlisted(verdict: Verdict, known: list[GenAnswer], skip: set[str]) -> list[GenAnswer]:
    """The verifier's source members that no answer or alias in `known` already covers."""
    listed = Prompt(id="", text="", hint="", golden="", answers=[(a.name, *a.aliases) for a in known])
    source = verdict.sources[0] if verdict.sources else "the official list"
    new: list[GenAnswer] = []
    for member in verdict.source_members:
        member = member.strip()
        # Exact and prefix matches only: a fuzzy match would pass "Erindale Studio Theatre" off as "Erindale Hall".
        if not member or normalize(member) in skip or match_answer(listed, member, fuzzy=False) is not None:
            continue
        # The same name with or without initials and titles ("David R. Peterson", "The Honourable Pauline McGibbon").
        words = _name_words(member)
        if any(_name_words(n) <= words or words <= _name_words(n) for names in listed.answers for n in names):
            continue
        new.append(GenAnswer(name=member, aliases=[], why=f"Listed on {source}."))
        listed = replace(listed, answers=[*listed.answers, (member,)])
    return new


def _name_words(name: str) -> frozenset[str]:
    """A name's distinctive words: no initials or honorifics. Empty for one-word names, which match nothing."""
    words = frozenset(w for w in normalize(name).split() if len(w) > 1) - NAME_TITLES
    return words if len(words) > 1 else frozenset({name})


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
        # Candidates that passed are kept across attempts: most get thrown out, so one batch rarely fills a day.
        checked: list[tuple[str, Prompt]] = []
        for attempt in range(1, self._attempts + 1):
            try:
                reply = self._writer.write(request, self._generator_model, RESPONSE_SCHEMA, GENERATOR_TEMPERATURE)
                gen = parse_reply(reply)
                verdicts = self._verify(gen)
                source = f"{self._generator_model} + {self._verifier_model}"
                checked += check_candidates(gen, verdicts)
                return pick_set(checked, recent), source
            except Exception as e:  # API errors and validation failures both get another try
                log.warning("attempt %d/%d failed: %s", attempt, self._attempts, e)
                last = e
        raise GenerationFailed(f"no valid set for {day} after {self._attempts} attempts") from last

    def _verify(self, gen: GenSet) -> Verdicts:
        """Checks each prompt in its own searching request. One that fails goes unjudged, which drops only it."""

        def check(prompt: GenPrompt) -> Verdict | None:
            try:
                reply = self._writer.write(
                    build_verify_request(prompt), self._verifier_model, VERDICT_SCHEMA, VERIFIER_TEMPERATURE, True
                )
                return parse_reply(reply, Verdict).model_copy(update={"id": prompt.id})
            except Exception as e:  # noqa: BLE001 - one bad check shouldn't sink the other prompts
                log.info("couldn't verify %s: %s", prompt.id, e)
                return None

        with ThreadPoolExecutor(VERIFY_WORKERS) as pool:
            return Verdicts(prompts=[v for v in pool.map(check, gen.prompts) if v is not None])


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
