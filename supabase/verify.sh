#!/usr/bin/env bash
# Checks that the Rarest Blue database is set up and locked down. Works on Supabase or plain Postgres.
#
#   supabase/verify.sh                 # reads DATABASE_URL (+ SUPABASE_URL, SUPABASE_ANON_KEY) from env or ./.env
#
# With SUPABASE_URL + SUPABASE_ANON_KEY it also calls the public REST and GraphQL APIs the way a stranger
# holding the (public) anon key would, and fails on anything but a clear refusal. It never prints response
# bodies or secrets. Exits non-zero on any failure. Read-only, except it deletes its own probe rows if a leak
# lets one land. Runs on macOS's bash 3.2. Needs psql, curl and python3.
set -uo pipefail
set -f  # probe paths and JSON contain ? and []; never glob

cd "$(dirname "$0")/.."

# Fill unset vars from .env without executing it (a password can hold $, ` or ;).
if [ -f .env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line=${line%$'\r'}; line=${line#export }
    case "$line" in DATABASE_URL=*|SUPABASE_URL=*|SUPABASE_ANON_KEY=*) ;; *) continue ;; esac
    k=${line%%=*}; v=${line#*=}; v=${v%\"}; v=${v#\"}; v=${v%\'}; v=${v#\'}
    [ -z "${!k:-}" ] && [ -n "$v" ] && export "$k=$v"
  done < .env
fi
if [ -z "${DATABASE_URL:-}" ]; then echo "Set DATABASE_URL (the Supabase pooler URI) in the env or .env"; exit 2; fi

fail=0
pass() { printf '  ok    %s\n' "$1"; }
bad()  { printf '  FAIL  %s\n' "$1"; fail=1; }
warn() { printf '  warn  %s\n' "$1"; }
finish() { if [ "$fail" = 0 ]; then echo "All checks passed."; exit 0; else echo "Some checks FAILED."; exit 1; fi; }

# Split the URL into libpq env vars so the password never shows up in `ps`.
envs=$(python3 -I - <<'PY'
import os, shlex, urllib.parse as u
p = u.urlsplit(os.environ["DATABASE_URL"])
if p.scheme not in ("postgresql", "postgres"): raise SystemExit(1)
p.port  # raises on a non-numeric port
qs = dict(u.parse_qsl(p.query))
env = {"PGHOST": p.hostname or "", "PGPORT": str(p.port or 5432), "PGUSER": u.unquote(p.username or ""),
       "PGPASSWORD": u.unquote(p.password or ""), "PGDATABASE": u.unquote(p.path.lstrip("/")) or "postgres",
       "PGSSLMODE": qs.get("sslmode", "")}
for k, v in env.items():
    print(f"export {k}={shlex.quote(v)}" if v else f"unset {k}")
local = (p.hostname or "") in ("", "localhost", "127.0.0.1", "::1") or (p.hostname or "").startswith("/")
print(f"IS_LOCAL={int(local)}")
PY
) || { echo "DATABASE_URL isn't a valid postgresql:// URI"; exit 2; }
eval "$envs"
unset DATABASE_URL

q() { psql -XAtq -v ON_ERROR_STOP=1 -c "$1"; }

echo "Database"
if ! q "SELECT 1" >/dev/null 2>&1; then bad "can't connect with DATABASE_URL"; finish; fi

for t in daily_prompts guesses finishes; do
  case "$(q "SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass('public.$t')")" in
    t) pass "$t exists with RLS on" ;;
    f) bad  "$t has RLS OFF" ;;
    *) bad  "$t is missing (run the migration)" ;;
  esac
done

n=$(q "SELECT count(*) FROM pg_policies WHERE schemaname = 'public' AND tablename IN ('daily_prompts', 'guesses', 'finishes')")
[ "$n" = 0 ] && pass "no RLS policies on the game tables" || bad "$n RLS policies on the game tables (none expected)"

if [ "${PGSSLMODE:-}" = require ] || [ "${PGSSLMODE:-}" = verify-ca ] || [ "${PGSSLMODE:-}" = verify-full ]; then
  pass "sslmode=${PGSSLMODE:-}"
elif [ "$IS_LOCAL" = 1 ]; then
  pass "local database, SSL not required"
else
  bad "remote database without sslmode=require in DATABASE_URL"
fi

# Anything in public that the API roles can touch. has_*_privilege counts PUBLIC grants, role membership and
# column grants, which information_schema views miss. Views and materialized views count: they skip RLS.
for r in anon authenticated; do
  if [ "$(q "SELECT count(*) FROM pg_roles WHERE rolname = '$r'")" = 0 ]; then
    pass "role $r absent (plain Postgres)"; continue
  fi
  rels=$(q "SELECT string_agg(c.relname, ', ') FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
              AND (has_table_privilege('$r', c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')
                   OR has_any_column_privilege('$r', c.oid, 'SELECT,INSERT,UPDATE'))")
  [ -z "$rels" ] && pass "$r can't read or write anything in public" || bad "$r has access to: $rels"
  fns=$(q "SELECT string_agg(p.oid::regprocedure::text, ', ') FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
           WHERE n.nspname = 'public' AND p.prorettype <> 'event_trigger'::regtype
             AND has_function_privilege('$r', p.oid, 'EXECUTE')")
  [ -z "$fns" ] && pass "$r can't call any function in public" || bad "$r can call (via /rest/v1/rpc): $fns"
done

others=$(q "SELECT string_agg(c.relname, ', ') FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relrowsecurity")
[ -z "$others" ] && pass "every table in public has RLS on" || bad "tables in public without RLS: $others"

[ "$(q "SELECT count(*) FROM pg_event_trigger WHERE evtname = 'rarest_blue_enable_rls' AND evtenabled <> 'D'")" = 1 ] \
  && pass "auto-RLS event trigger installed" || warn "auto-RLS event trigger missing: enable RLS by hand on new tables"

[ -n "${SUPABASE_URL:-}" ] && [ -n "${SUPABASE_ANON_KEY:-}" ] || {
  echo "(set SUPABASE_URL and SUPABASE_ANON_KEY to also probe the public APIs)"; finish; }

echo "Public APIs (as anon)"
BASE=${SUPABASE_URL%/}
# Legacy anon keys are JWTs and go in Authorization too; new sb_publishable_ keys go in apikey only.
auth=(-H "apikey: $SUPABASE_ANON_KEY")
case "$SUPABASE_ANON_KEY" in eyJ*) auth+=(-H "Authorization: Bearer $SUPABASE_ANON_KEY") ;; esac

# call METHOD PATH [JSON]: sets CODE (HTTP status, 000 on network failure) and ERR (PostgREST error code).
call() {
  local out
  out=$(curl -sS --max-time 15 -X "$1" "${auth[@]}" -H "Content-Type: application/json" -H "Prefer: return=minimal" \
        ${3:+-d "$3"} -w '\n%{http_code}' "$BASE$2" 2>/dev/null) || out=$'\n000'
  CODE=${out##*$'\n'}
  BODY=${out%$'\n'*}
  ERR=$(printf '%s' "$BODY" | python3 -Ic 'import json,sys
try: d=json.load(sys.stdin); print(d.get("code","") if isinstance(d,dict) else "")
except Exception: print("")')
}

# Control request: an unknown table must give PostgREST's "not found". That proves the URL is right and the key
# was accepted, so the refusals below mean something. A bad key gives 401 here instead.
call GET /rest/v1/rarest_blue_no_such_table
if [ "$CODE" = 404 ] && { [ "$ERR" = PGRST205 ] || [ "$ERR" = 42P01 ]; }; then
  pass "REST API reachable and key accepted"
else
  bad "control request got HTTP $CODE ${ERR:+($ERR)}: check SUPABASE_URL / SUPABASE_ANON_KEY, or the Data API is off"
  finish
fi

probe_day=1999-01-01; probe_id=verify-probe-0000
for t in daily_prompts guesses finishes; do
  call GET "/rest/v1/$t?select=*&limit=1"
  if [ "$ERR" = 42501 ] || { [ "$CODE" = 200 ] && [ "$BODY" = "[]" ]; }; then
    pass "read $t refused (${ERR:-empty})"
  else
    bad "read $t returned HTTP $CODE ${ERR:+($ERR)}"
  fi
done

writes=(
  "POST /rest/v1/daily_prompts {\"day\":\"$probe_day\",\"prompts\":[],\"source\":\"verify-probe\"}"
  "POST /rest/v1/guesses {\"day\":\"$probe_day\",\"prompt_id\":\"p\",\"player_id\":\"$probe_id\",\"raw\":\"x\",\"points\":0,\"share\":0}"
  "POST /rest/v1/finishes {\"day\":\"$probe_day\",\"player_id\":\"$probe_id\",\"nickname\":\"probe\",\"score\":0}"
  "PATCH /rest/v1/finishes?day=eq.$probe_day {\"score\":1}"
  "DELETE /rest/v1/finishes?day=eq.$probe_day"
)
leaked=0
for w in "${writes[@]}"; do
  set -- $w
  call "$1" "$2" "${3:-}"
  if [ "$ERR" = 42501 ]; then pass "$1 ${2%%\?*} refused"
  else bad "$1 ${2%%\?*} returned HTTP $CODE ${ERR:+($ERR)}"; leaked=1; fi
done
if [ "$leaked" = 1 ]; then
  q "DELETE FROM public.daily_prompts WHERE day = '$probe_day';
     DELETE FROM public.guesses WHERE day = '$probe_day';
     DELETE FROM public.finishes WHERE day = '$probe_day';" >/dev/null 2>&1 || true
fi

call POST /graphql/v1 '{"query":"{ __schema { queryType { fields { name } } } }"}'
if [ "$CODE" = 000 ]; then
  bad "GraphQL endpoint unreachable"
elif printf '%s' "$BODY" | grep -Eqi 'daily_?prompts|guesses|finishes'; then
  bad "GraphQL exposes a game table to anon"
else
  pass "GraphQL exposes no game tables (HTTP $CODE)"
fi

finish
