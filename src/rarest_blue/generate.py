"""Nightly job: ask an LLM (via OpenRouter) for tomorrow's prompt set and store it.

Run with `python -m rarest_blue.generate` from src/. Scheduled at 23:30 Toronto
time; at midnight the API starts serving the stored set. Exits non-zero if no
valid set could be stored so the scheduler retries.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import date, timedelta
from typing import Literal

import httpx
from pydantic import BaseModel

from . import db, game
from .prompts import PROMPTS_BY_ID, Prompt, to_dict

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Tried in order, one per attempt. Free models are rate-limited and come and go, so list a few.
MODELS = os.environ.get(
    "OPENROUTER_MODELS", "particle-ai/particle-1:free,nvidia/nemotron-3.5-super-vl:free,openrouter/free"
).split(",")
MIN_ANSWERS = 15
GOLDEN_MIN_INDEX = 3
# The golden answer must sit in the last part of the list, past this fraction of it.
GOLDEN_MIN_FRACTION = 2 / 3
# Every prompt must name UofT or one of its places, so nothing drifts into general trivia.
UOFT_ANCHORS = (
    "uoft", "u of t", "university of toronto", "st. george", "st george", "utm", "utsc", "mississauga",
    "scarborough", "varsity", "robarts", "hart house", "sid smith", "bahen", "con hall", "convocation hall",
    "skule", "arts & sci", "arts and sci", "first-year", "frosh", "college",
)
ATTEMPTS = 3
# Free models took 2-6 minutes per set in testing.
REQUEST_TIMEOUT_SECONDS = 420
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


INSTRUCTIONS = f"""\
You write the daily prompt set for UofT Krillion, a trivia game for University of Toronto students.
Players get a prompt like "Name a St. George college" and type any valid answer. The fewer
players who give the same answer, the more points they score, so every prompt needs a
large, complete, factually accurate list of valid answers.

Write exactly {game.PROMPTS_PER_DAY} prompts. Rules:
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
    return json.dumps({"prompts": [{**to_dict(p), "category": c} for p, c in picks]}, indent=1)


def _strict(schema: dict) -> dict:
    """Mark every object closed, as strict JSON-schema mode requires."""
    for obj in [schema, *schema.get("$defs", {}).values()]:
        if obj.get("type") == "object":
            obj["additionalProperties"] = False
    return schema


RESPONSE_SCHEMA = _strict(GenSet.model_json_schema())


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
        key = game.normalize(name)
        if not key or key in taken:
            continue
        names = [name]
        taken.add(key)
        for alias in ans.aliases:
            alias_key = game.normalize(alias)
            if alias_key and alias_key not in taken:
                names.append(alias.strip())
                taken.add(alias_key)
        answers.append(tuple(names))

    if len(answers) < MIN_ANSWERS:
        raise ValueError(f"{gen.id}: only {len(answers)} usable answers")

    canon = [names[0] for names in answers]
    golden = next((n for n in canon if game.normalize(n) == game.normalize(gen.golden)), None)
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
        decoy, key = decoy.strip(), game.normalize(decoy)
        if key and key not in taken and key not in decoys and game.match_answer(prompt, decoy) is None:
            decoys[key] = decoy
    return Prompt(**{**prompt.__dict__, "decoys": list(decoys.values())})


def clean_set(gen: GenSet) -> list[Prompt]:
    if len(gen.prompts) < game.PROMPTS_PER_DAY:
        raise ValueError(f"got {len(gen.prompts)} prompts, need {game.PROMPTS_PER_DAY}")
    prompts = [clean_prompt(p) for p in gen.prompts[: game.PROMPTS_PER_DAY]]
    ids = [p.id for p in prompts]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate prompt ids: {ids}")
    category, n = Counter(p.category for p in gen.prompts[: game.PROMPTS_PER_DAY]).most_common(1)[0]
    if n > MAX_PER_CATEGORY:
        raise ValueError(f"{n} prompts are '{category}', max is {MAX_PER_CATEGORY}")
    return prompts


def ask_llm(request: str, model: str) -> GenSet:
    response = httpx.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "X-Title": "UofT Krillion"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": request}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "prompt_set", "strict": True, "schema": RESPONSE_SCHEMA},
            },
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    if "error" in body:
        raise ValueError(f"OpenRouter error: {body['error']}")
    content = body["choices"][0]["message"]["content"] or ""
    # Some models wrap JSON in a code fence even when asked not to.
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    return GenSet.model_validate_json(content)


def generate(day: date, avoid: list[str]) -> tuple[list[Prompt], str]:
    """Returns the cleaned set and the model that wrote it."""
    request = build_request(avoid)
    errors = []
    for attempt in range(1, ATTEMPTS + 1):
        model = MODELS[(attempt - 1) % len(MODELS)].strip()
        try:
            return clean_set(ask_llm(request, model)), model
        except Exception as e:  # API errors and validation failures both get another try
            print(f"attempt {attempt}/{ATTEMPTS} ({model}) failed: {e}", file=sys.stderr)
            errors.append(e)
    raise RuntimeError(f"no valid set for {day} after {ATTEMPTS} attempts") from errors[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--day", type=date.fromisoformat, help="day to generate (default: tomorrow in Toronto)")
    parser.add_argument("--dry-run", action="store_true", help="print the set instead of storing it")
    args = parser.parse_args(argv)
    day = args.day or game.today() + timedelta(days=1)

    db.init_schema()
    with db.connect() as conn:
        if not args.dry_run and db.load_prompts(conn, day) is not None:
            print(f"{day} already has a set; nothing to do")
            return 0
        avoid = db.recent_prompt_texts(conn, day, AVOID_RECENT_DAYS)

    try:
        prompts, model = generate(day, avoid)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1

    if args.dry_run:
        print(json.dumps([to_dict(p) for p in prompts], indent=2))
        return 0
    with db.connect() as conn:
        stored = db.save_prompts(conn, day, prompts, source=model)
    print(f"{day}: {'stored' if stored else 'already had a set, kept it'} ({', '.join(p.id for p in prompts)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
