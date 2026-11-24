"""Nightly job: have an LLM write tomorrow's prompt set, fact-check it with a second LLM, and store it.

    python -m rarest_blue.entrypoints.cli.generate [--day YYYY-MM-DD] [--dry-run]

Scheduled at 23:30 Toronto time. It writes the set for two days out, so each set sits stored for a full day where
someone can read it (and fix it with the review tool) before the API starts serving it. Exits non-zero if no valid set
could be stored, so the Cloud Run job retries.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta

from ...application.generation import GenerationFailed, Outcome, PromptSetGenerator, run_nightly
from ...application.ports import PromptWriter
from ...config import Settings
from ...domain import days
from ...infrastructure import postgres
from ...infrastructure.openrouter import OpenRouterWriter

# Generate this far ahead so a day's set can be read before it goes live.
DAYS_AHEAD = 2


def main(argv: list[str] | None = None, settings: Settings | None = None, writer: PromptWriter | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--day", type=date.fromisoformat, help="day to generate (default: two days out)")
    parser.add_argument("--dry-run", action="store_true", help="print the set instead of storing it")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    settings = settings or Settings.from_env()
    day = args.day or days.today() + timedelta(days=DAYS_AHEAD)

    postgres.init_schema(settings.database_url)
    generator = PromptSetGenerator(
        writer or OpenRouterWriter(settings.openrouter_api_key), settings.generator_model, settings.verifier_model
    )
    try:
        result = run_nightly(lambda: postgres.PostgresUnitOfWork(settings.database_url), generator, day, args.dry_run)
    except GenerationFailed as e:
        print(e, file=sys.stderr)
        return 1

    if result.outcome is Outcome.DRY_RUN:
        print(json.dumps([p.to_dict() for p in result.prompts], indent=2))
    elif result.outcome is Outcome.SKIPPED:
        print(f"{day} already has a set; nothing to do")
    elif result.outcome is Outcome.ALREADY_HAD_SET:
        print(f"{day}: already had a set, kept it ({', '.join(p.id for p in result.prompts)})")
    else:
        print(f"{day}: stored ({', '.join(p.id for p in result.prompts)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
