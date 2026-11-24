"""Check a hand-edited prompt set before pushing it (see supabase/prompts.sh).

    python -m rarest_blue.entrypoints.cli.prompts check FILE.json

Exits 1 if the set has errors that would break the day; warnings are printed but don't fail.
"""

from __future__ import annotations

import argparse
import json
import sys

from ...application.editing import check_set, parse_set


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    chk = sub.add_parser("check", help="validate an edited set")
    chk.add_argument("file")
    args = parser.parse_args(argv)

    try:
        with open(args.file, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"can't read {args.file}: {e}", file=sys.stderr)
        return 1

    prompts, report = parse_set(data)
    check_set(prompts, report)
    for w in report.warnings:
        print(f"  warn   {w}")
    for e in report.errors:
        print(f"  ERROR  {e}")
    print(f"{len(prompts)} prompts: {len(report.errors)} errors, {len(report.warnings)} warnings")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
