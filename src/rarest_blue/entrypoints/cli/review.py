"""Review rejected guesses and accept the real answers the list missed.

    python -m rarest_blue.entrypoints.cli.review                    # today's most common rejected guesses
    python -m rarest_blue.entrypoints.cli.review accept subway "Spadina Stn" --as Spadina   # new alias
    python -m rarest_blue.entrypoints.cli.review accept subway "Dupont"                     # new answer
    python -m rarest_blue.entrypoints.cli.review auto [--dry-run]   # an LLM judges rejected guesses, accepts real ones

Accepting updates the stored set and rescores every guess it now matches, including players' leaderboard totals.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from ...application import review
from ...config import Settings
from ...domain import days
from ...infrastructure import postgres
from ...infrastructure.openrouter import OpenRouterWriter


def main(argv: list[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--day", type=date.fromisoformat, help="default: today in Toronto")
    sub = parser.add_subparsers(dest="command")
    listing = sub.add_parser("list", help="show the most common rejected guesses (default)")
    listing.add_argument("--limit", type=int, default=10, help="guesses per prompt")
    acc = sub.add_parser("accept", help="accept a guess and rescore")
    acc.add_argument("prompt_id")
    acc.add_argument("guess")
    acc.add_argument("--as", dest="as_answer", help="existing answer to add the guess to as an alias")
    auto = sub.add_parser("auto", help="have an LLM judge rejected guesses and accept the real answers")
    auto.add_argument("--dry-run", action="store_true", help="print what it would accept, change nothing")
    args = parser.parse_args(argv)

    settings = settings or Settings.from_env()
    day = args.day or days.today()

    with postgres.PostgresUnitOfWork(settings.database_url) as uow:
        if args.command == "auto":
            logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
            writer = OpenRouterWriter(settings.openrouter_api_key)
            done = review.auto_accept(uow, writer, settings.judge_model, day, args.dry_run)
            for pid, guess, same_as, n in done:
                print(
                    f"{'would accept' if args.dry_run else 'accepted'} {pid}: '{guess}'"
                    f"{f' as {same_as}' if same_as else ''}{'' if args.dry_run else f' (rescored {n})'}"
                )
            print(f"{len(done)} guesses {'judged valid' if args.dry_run else 'accepted'} on {day}")
            return 0
        if args.command == "accept":
            try:
                n = review.accept(uow, day, args.prompt_id, args.guess, args.as_answer)
            except ValueError as e:
                print(e, file=sys.stderr)
                return 1
            print(f"accepted '{args.guess}' for {args.prompt_id} on {day}; rescored {n} guesses")
            return 0
        found = review.rejected(uow, day, getattr(args, "limit", 10))

    if not found:
        print(f"no rejected guesses on {day}")
    for pid, guesses in found.items():
        print(pid)
        for raw, n in guesses:
            print(f"  {n:>4}  {raw}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
