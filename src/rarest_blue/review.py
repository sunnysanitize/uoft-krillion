"""Review rejected guesses and accept the real answers the list missed.

    python -m rarest_blue.review                    # today's most common rejected guesses
    python -m rarest_blue.review accept subway "Spadina Stn" --as Spadina   # new alias
    python -m rarest_blue.review accept subway "Dupont"                     # new answer

Accepting updates the stored set and rescores every guess it now matches,
including players' leaderboard totals.
"""

import argparse
import sys
from collections import Counter, defaultdict
from datetime import date

from . import db, game
from .prompts import Prompt


def rejected(conn, day: date, limit: int) -> dict[str, list[tuple[str, int]]]:
    """Most common rejected guesses per prompt, as (example spelling, count)."""
    rows = conn.execute(
        "SELECT prompt_id, raw FROM guesses WHERE day = %s AND answer IS NULL", (day.isoformat(),)
    ).fetchall()
    counts: dict[str, Counter] = defaultdict(Counter)
    spelling: dict[str, str] = {}
    for row in rows:
        key = game.normalize(row["raw"])
        if key:
            counts[row["prompt_id"]][key] += 1
            spelling.setdefault(key, row["raw"].strip())
    return {pid: [(spelling[k], n) for k, n in c.most_common(limit)] for pid, c in counts.items()}


def with_answer(prompt: Prompt, guess: str, as_answer: str | None) -> Prompt:
    """The prompt with `guess` accepted, as an alias of `as_answer` or as a new answer."""
    guess = guess.strip()
    answers = list(prompt.answers)
    if as_answer is not None:
        canon = game.match_answer(prompt, as_answer)
        if canon is None:
            raise ValueError(f"'{as_answer}' isn't an answer to {prompt.id}")
        current = game.match_answer(prompt, guess)
        if current not in (None, canon):
            raise ValueError(f"'{guess}' already counts as '{current}'")
        if current is None:
            answers = [names + (guess,) if names[0] == canon else names for names in answers]
    elif game.match_answer(prompt, guess) is None:
        answers.append((guess,))
    updated = Prompt(**{**prompt.__dict__, "answers": answers})
    # A decoy that now scores would mislead the autocomplete.
    decoys = [d for d in prompt.decoys if game.match_answer(updated, d) is None]
    return Prompt(**{**updated.__dict__, "decoys": decoys})


def accept(conn, day: date, prompt_id: str, guess: str, as_answer: str | None = None) -> int:
    """Accept a guess and rescore what it matches. Returns how many guesses were rescored."""
    key = day.isoformat()
    prompt = next((p for p in db.load_prompts(conn, day) or [] if p.id == prompt_id), None)
    if prompt is None:
        raise ValueError(f"no prompt '{prompt_id}' on {key}")
    prompt = with_answer(prompt, guess, as_answer)
    db.replace_prompt(conn, day, prompt)

    rows = conn.execute(
        "SELECT player_id, raw FROM guesses WHERE day = %s AND prompt_id = %s AND answer IS NULL", (key, prompt_id)
    ).fetchall()
    fixed = {r["player_id"]: a for r in rows if (a := game.match_answer(prompt, r["raw"])) is not None}
    if not fixed:
        return 0
    for player_id, answer in fixed.items():
        conn.execute(
            "UPDATE guesses SET answer = %s WHERE day = %s AND prompt_id = %s AND player_id = %s",
            (answer, key, prompt_id, player_id),
        )
    # Score with the counts after the fix, so the newly accepted answers aren't all "rare".
    counts = db.answer_counts(conn, key, prompt)
    total = sum(counts.values())
    for player_id, answer in fixed.items():
        share = counts[answer] / total
        points = game.score(share) + (game.GOLDEN_BONUS if answer == prompt.golden else 0)
        conn.execute(
            "UPDATE guesses SET points = %s, share = %s WHERE day = %s AND prompt_id = %s AND player_id = %s",
            (points, share, key, prompt_id, player_id),
        )
    conn.execute(
        "UPDATE finishes f SET score = (SELECT COALESCE(SUM(points), 0) FROM guesses g "
        "WHERE g.day = f.day AND g.player_id = f.player_id) WHERE day = %s AND player_id = ANY(%s)",
        (key, list(fixed)),
    )
    return len(fixed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--day", type=date.fromisoformat, help="default: today in Toronto")
    sub = parser.add_subparsers(dest="command")
    listing = sub.add_parser("list", help="show the most common rejected guesses (default)")
    listing.add_argument("--limit", type=int, default=10, help="guesses per prompt")
    acc = sub.add_parser("accept", help="accept a guess and rescore")
    acc.add_argument("prompt_id")
    acc.add_argument("guess")
    acc.add_argument("--as", dest="as_answer", help="existing answer to add the guess to as an alias")
    args = parser.parse_args(argv)
    day = args.day or game.today()

    with db.connect() as conn:
        if args.command == "accept":
            try:
                n = accept(conn, day, args.prompt_id, args.guess, args.as_answer)
            except ValueError as e:
                print(e, file=sys.stderr)
                return 1
            print(f"accepted '{args.guess}' for {args.prompt_id} on {day}; rescored {n} guesses")
            return 0
        found = rejected(conn, day, getattr(args, "limit", 10))
    if not found:
        print(f"no rejected guesses on {day}")
    for pid, guesses in found.items():
        print(pid)
        for raw, n in guesses:
            print(f"  {n:>4}  {raw}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
