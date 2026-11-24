"""Answer matching: turn whatever a player typed into a canonical answer, or None."""

import difflib
import re
import unicodedata
from dataclasses import replace

from .models import Prompt

_FILLER = {"the", "of", "and", "a", "at", "uoft", "u", "t"}
# Trailing words players often add or leave off ("Spadina Station", "Innis Library").
_GENERIC = {
    "library",
    "hall",
    "building",
    "centre",
    "center",
    "college",
    "street",
    "avenue",
    "ave",
    "road",
    "station",
    "house",
    "residence",
    "school",
    "faculty",
    "university",
    "laboratory",
    "laboratories",
    "lab",
    "labs",
}
# Shortest guess that may stand in for a longer answer it starts ("Bahen" for "Bahen Centre").
MIN_PREFIX_CHARS = 4
# Typos are only forgiven on keys at least this long, so "MAT" can't fuzz into "MAT137".
MIN_FUZZY_CHARS = 5
FUZZY_CUTOFF = 0.85
# How close an unrecognized guess must be to a known name to offer "did you mean".
SUGGEST_CUTOFF = 0.7


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.lower().replace("&", " and ").replace("'", "")
    text = re.sub(r"\bst\b\.?", "saint", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(w for w in text.split() if w not in _FILLER)


def match_answer(prompt: Prompt, guess: str, fuzzy: bool = True) -> str | None:
    """Return the canonical answer the guess refers to, or None if invalid."""
    key = normalize(guess)
    if not key:
        return None
    index = _alias_index(prompt)
    if key in index:
        return index[key]
    key = _strip_generic(key)
    if key in index:
        return index[key]
    # A distinctive leading part of exactly one answer counts ("Sidney Smith" for "Sidney Smith Hall").
    if len(key) >= MIN_PREFIX_CHARS and not set(key.split()) <= _GENERIC:
        hits = {canon for alias, canon in index.items() if alias.startswith(key + " ")}
        if len(hits) == 1:
            return hits.pop()
    if fuzzy and len(key) >= MIN_FUZZY_CHARS:
        close = difflib.get_close_matches(key, index.keys(), n=1, cutoff=FUZZY_CUTOFF)
        if close:
            return index[close[0]]
    return None


def recognize(prompt: Prompt, guess: str) -> tuple[bool, str | None]:
    """Is the guess a known answer or decoy? If not, the closest known name to suggest.

    Answers and decoys are treated alike, so this never reveals which is which.
    """
    known = replace(prompt, answers=[*prompt.answers, *((d,) for d in prompt.decoys)])
    if match_answer(known, guess, fuzzy=False) is not None:
        return True, None
    key = _strip_generic(normalize(guess))
    if len(key) < 3:
        return False, None
    index = _alias_index(known)
    # Compare with generic words dropped on both sides, so "Masey College" finds "Massey College".
    for alias, canon in list(index.items()):
        index.setdefault(_strip_generic(alias), canon)
    close = difflib.get_close_matches(key, index.keys(), n=1, cutoff=SUGGEST_CUTOFF)
    return False, index[close[0]] if close else None


def _alias_index(prompt: Prompt) -> dict[str, str]:
    index: dict[str, str] = {}
    for names in prompt.answers:
        for name in names:
            index.setdefault(normalize(name), names[0])
    return index


def _strip_generic(key: str) -> str:
    words = key.split()
    while len(words) > 1 and words[-1] in _GENERIC:
        words.pop()
    return " ".join(words)
