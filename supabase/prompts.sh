#!/usr/bin/env bash
# Review and edit a day's prompt set in the hosted database with the Supabase CLI.
#
#   supabase/prompts.sh list                 # stored days, newest first
#   supabase/prompts.sh pull 2026-11-25      # -> supabase/prompts/2026-11-25.json (edit this)
#   supabase/prompts.sh check 2026-11-25     # validate your edits without touching the database
#   supabase/prompts.sh push 2026-11-25      # validate, back up what's stored, then replace it
#   DRY_RUN=out.sql supabase/prompts.sh push 2026-11-25   # write the SQL to out.sql instead of running it
#
# The nightly job writes the set for two days out, so a day can be edited until it goes live at midnight Toronto
# time. Pushing to a day that's already live is refused: players' guesses were scored against the old answers.
# If a day has no stored set, `pull` starts you from the built-in fallback set the game would otherwise serve.
#
# Needs: supabase CLI (logged in and linked, see supabase/README.md) and src/.venv for the checks.
# The JSON files hold every answer, so supabase/prompts/ is gitignored. Never commit or share them.
set -euo pipefail

cd "$(dirname "$0")/.."
DIR=supabase/prompts
PY=src/.venv/bin/python
TAG='rb_prompts_json'   # dollar-quote tag for the SQL literal

die() { echo "error: $*" >&2; exit 1; }
need_day() {
  [[ "${1:-}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || die "give a day as YYYY-MM-DD"
  date -j -f %F "$1" +%F >/dev/null 2>&1 || date -d "$1" +%F >/dev/null 2>&1 || die "$1 isn't a real date"
}
need_py() { [ -x "$PY" ] || die "set up the backend venv first: cd src && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; }
query_ro() { supabase db query --remote --read-only "$1" -o json </dev/null 2>/dev/null; }
# The CLI prints a bare list of rows in a terminal but wraps them as {"rows": [...]} for agents.
rows() { python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps(d if isinstance(d, list) else d.get("rows", [])))'; }
today() { TZ=America/Toronto date +%F; }

cmd=${1:-}; day=${2:-}
mkdir -p "$DIR" "$DIR/backups"

case "$cmd" in
  list)
    query_ro "select day, source, jsonb_array_length(prompts) as prompts,
                     (select count(*) from guesses g where g.day = d.day) as guesses
              from daily_prompts d order by day desc limit 14" | rows | python3 -c '
import json, sys
fmt = "{:<12}{:>8}{:>9}  {}"
print(fmt.format("day", "prompts", "guesses", "source"))
for r in json.load(sys.stdin):
    print(fmt.format(r["day"], r["prompts"], r["guesses"], r["source"]))'
    echo "today (Toronto): $(today). Days after today can still be edited."
    ;;

  pull)
    need_day "$day"; need_py
    out="$DIR/$day.json"
    [ ! -e "$out" ] || die "$out already exists; delete it first if you want a fresh copy"
    stored=$(query_ro "select prompts from daily_prompts where day = '$day'" | rows)
    if [ "$stored" = "[]" ]; then
      echo "$day has no stored set; starting from the fallback set the game would serve that day."
      PYTHONPATH=src "$PY" -c '
import json, sys
from datetime import date
from rarest_blue.domain import days
from rarest_blue.domain.prompt_bank import PROMPTS
print(json.dumps([p.to_dict() for p in days.pick_fallback(date.fromisoformat(sys.argv[1]), PROMPTS)], indent=2, ensure_ascii=False))
' "$day" > "$out"
    else
      python3 -c 'import json,sys; p=json.loads(sys.argv[1])[0]["prompts"]; p=json.loads(p) if isinstance(p,str) else p; print(json.dumps(p, indent=2, ensure_ascii=False))' "$stored" > "$out"
    fi
    echo "wrote $out. Edit it, then: supabase/prompts.sh check $day && supabase/prompts.sh push $day"
    ;;

  check)
    need_day "$day"; need_py
    [ -f "$DIR/$day.json" ] || die "no $DIR/$day.json; run: supabase/prompts.sh pull $day"
    PYTHONPATH=src "$PY" -m rarest_blue.entrypoints.cli.prompts check "$DIR/$day.json"
    ;;

  push)
    need_day "$day"; need_py
    file="$DIR/$day.json"
    [ -f "$file" ] || die "no $file; run: supabase/prompts.sh pull $day"
    [[ "$day" > "$(today)" ]] || die "$day is already live or past (today is $(today)); players were scored against it"

    PYTHONPATH=src "$PY" -m rarest_blue.entrypoints.cli.prompts check "$file" || die "fix the errors above first"

    played=$(query_ro "select count(*) as n from guesses where day = '$day'" | rows | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["n"])')
    [ "$played" = 0 ] || die "$day already has $played guesses; refusing to change answers under them"

    # Keep what's stored now, so a bad push can be undone by pushing the backup.
    backup="$DIR/backups/$day-$(date +%Y%m%d-%H%M%S).json"
    query_ro "select prompts from daily_prompts where day = '$day'" | rows > "$backup"
    echo "backed up the stored set to $backup"

    json=$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])), ensure_ascii=False, separators=(",", ":")))' "$file")
    [[ "$json" != *"\$$TAG\$"* ]] || die "the file contains \$$TAG\$, which would break the SQL quoting"
    sql=$(mktemp)
    trap 'rm -f "$sql"' EXIT
    cat > "$sql" <<SQL
INSERT INTO public.daily_prompts (day, prompts, source)
VALUES ('$day', \$$TAG\$$json\$$TAG\$::jsonb, 'edited by hand')
ON CONFLICT (day) DO UPDATE SET prompts = EXCLUDED.prompts, source = EXCLUDED.source;
SQL
    if [ -n "${DRY_RUN:-}" ]; then cp "$sql" "$DRY_RUN"; echo "DRY_RUN: wrote the SQL to $DRY_RUN, database untouched"; exit 0; fi
    echo "pushing $day to the hosted database (the CLI will ask you to confirm)..."
    supabase db query --remote -f "$sql"
    echo "done. Check it: supabase/prompts.sh list"
    ;;

  *)
    sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
