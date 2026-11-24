# Supabase

Supabase is the production Postgres for Rarest Blue. It holds three tables:

| Table | What's in it |
|---|---|
| `daily_prompts` | One row per day: the 7 prompts the nightly LLM job wrote (answers, aliases, decoys, golden krill), plus `source` (the model name, or `fallback`) |
| `guesses` | Every player's answer to every prompt, with the points and rarity share it scored |
| `finishes` | Each player's final score, nickname and college for the day (the leaderboard) |

The FastAPI backend is the only thing that talks to the database. It connects as the `postgres` role over
`DATABASE_URL` and doesn't use Supabase's REST API, auth or client libraries. The browser never talks to Supabase.

## Why it's locked down

Supabase publishes every table in `public` through a REST API, and anyone can lift the anon key from a browser.
Without the lockdown, one `curl` would return today's answers and golden krill and let anyone write fake scores.
The migration:

- turns on row level security with **no policies**, so the API sees zero rows even if a grant comes back;
- revokes every table and sequence grant from `anon` and `authenticated`, and removes the default that lets
  anyone (`PUBLIC`) call new functions, since a function in `public` is callable at `/rest/v1/rpc/<name>`;
- adds an event trigger that turns RLS on for any table created in `public` later;
- adds checks that mirror the API's own limits (ISO day, player id length, answer ≤ 80 chars, nickname ≤ 20, share in 0–1).

The table definitions match `SCHEMA` in `src/rarest_blue/db.py`. If you change one, change the other.

## Setup

1. Create a Supabase project and save the database password in a password manager.
2. In **Connect → Transaction pooler**, copy the URI (port 6543). Add `?sslmode=require` and put it in `.env` as
   `DATABASE_URL`. The backend already turns off prepared statements, which the transaction pooler needs.
3. Apply the migration with any one of these:
   - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/20261123000000_rarest_blue_init.sql`
   - paste the file into the dashboard's **SQL Editor** and run it
   - `supabase db push` (Supabase CLI, after `supabase init` and `supabase link`)
4. Check it: `supabase/verify.sh`. It reads `.env` (without executing it) and passes the password to `psql` through
   the environment, never on the command line. If `SUPABASE_URL` and `SUPABASE_ANON_KEY` are set, it also calls the
   REST and GraphQL APIs as a stranger would. It fails if the key is rejected, or if any read returns rows or any
   write gets through.
5. Set the same `DATABASE_URL` on the API host and on the nightly `python -m rarest_blue.generate` job.

The migration is idempotent, so it doesn't matter whether it runs before or after the backend first boots
(`db.init_schema` only runs `CREATE TABLE IF NOT EXISTS`). Run `verify.sh` again after any schema change.

## Keeping it safe

- `DATABASE_URL` is the master key. Keep it in `.env` (gitignored) and the host's secret store, never in `web/` or in
  any `NEXT_PUBLIC_*` variable.
- The backend doesn't need the Data API, so you can turn it off in the dashboard's Data API settings. That's a
  second lock on the same door. Run `verify.sh` without the anon key afterwards, since the REST probe needs the API on.
- Free-tier projects pause after about a week without database activity. Daily play keeps the game awake, but
  check your plan's backup policy before you rely on it, since the free tier doesn't include automatic backups.
- `ALTER DEFAULT PRIVILEGES` only covers objects that `postgres` creates. If you add tables or functions some
  other way (dashboard Table Editor, extensions), run `verify.sh` afterwards.
