# Supabase

Supabase is the production Postgres for Rarest Blue. It holds three tables:

| Table | What's in it |
|---|---|
| `daily_prompts` | One row per day: the 7 prompts the nightly LLM job wrote (answers, aliases, decoys, golden krill), plus `source` (the model name, or `fallback`) |
| `guesses` | Every player's answer to every prompt, with the points and rarity share it scored |
| `finishes` | Each player's final score and nickname for the day (the leaderboard) |

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

The table definitions match `SCHEMA` in `src/rarest_blue/infrastructure/postgres.py`. If you change one, change the other.

## Setup

1. Create a Supabase project and save the database password in a password manager.
2. In **Connect → Transaction pooler**, copy the URI (port 6543). Add `?sslmode=require` and put it in `.env` as
   `DATABASE_URL`. The backend already turns off prepared statements, which the transaction pooler needs.
3. Apply the migrations, in filename order, with any one of these:
   - `for f in supabase/migrations/*.sql; do psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f "$f"; done`
   - paste the file into the dashboard's **SQL Editor** and run it
   - `supabase db push` (Supabase CLI, after `supabase init` and `supabase link`)
4. Check it: `supabase/verify.sh`. It reads `.env` (without executing it) and passes the password to `psql` through
   the environment, never on the command line. If `SUPABASE_URL` and `SUPABASE_ANON_KEY` are set, it also calls the
   REST and GraphQL APIs as a stranger would. It fails if the key is rejected, or if any read returns rows or any
   write gets through.
5. Set the same `DATABASE_URL` on the API host and on the nightly generator job (`deploy/setup.sh` stores it in Secret Manager for both).

The migration is idempotent, so it doesn't matter whether it runs before or after the backend first boots
(`postgres.init_schema` only runs `CREATE TABLE IF NOT EXISTS`). Run `verify.sh` again after any schema change.

## Supabase CLI

`supabase/config.toml` is checked in, so the CLI works from the repo root. One-time per machine:

```bash
supabase login                                   # opens the browser
supabase link --project-ref glwmhcxhxjbbevgtydyv # asks for the database password
```

Then, for the hosted project, always pass `--remote` (without it the CLI targets a local Docker stack):

```bash
supabase migration list --remote   # local vs applied migrations
supabase db push --remote          # apply new files in supabase/migrations/
supabase/verify.sh                 # re-check the lockdown afterwards
```

New schema changes go in a new file in `supabase/migrations/` (`supabase migration new <name>`). Don't edit an
applied migration. Mirror the change in `SCHEMA` in `src/rarest_blue/infrastructure/postgres.py`.

## Editing a day's questions

At 23:30 Toronto time the nightly job stores the set for **two days out**, so every set sits in the database for
about a day before it goes live at midnight. Review or replace it in that window:

```bash
supabase/prompts.sh list                # stored days, guess counts, and today's date
supabase/prompts.sh pull 2026-11-25     # writes supabase/prompts/2026-11-25.json: edit it
supabase/prompts.sh check 2026-11-25    # errors would break the day; warnings are just quality hints
supabase/prompts.sh push 2026-11-25     # checks, backs up what's stored, then replaces it (asks to confirm)
```

In the file, each prompt has `text`, `hint`, `answers` (each one a list: canonical name first, then aliases),
`golden` (copied exactly from an answer's first name) and `decoys` (wrong answers the game recognizes). If a day
has no stored set, `pull` starts you from the fallback set the game would serve. Pushing a day that's already live
is refused, because players were scored against it. To undo a push, copy the backup from
`supabase/prompts/backups/` over the day's file and push again. `supabase/prompts/` is gitignored because the
files hold every answer.

## Reviewing in Discord

A bot posts each new set to a private Discord channel about 20 minutes after the generator runs, and reviewers fix it
there: `/add-answer`, `/add-alias`, `/remove-answer`, `/remove-decoy` and `/set-golden` post a checked suggestion with
an **Apply** button, and `/review` reposts any stored day. Until a day goes live any fix can go in; once it's being
played, only new answers and aliases, which rescore the players who typed them (like `review accept`).

1. In the [Discord developer portal](https://discord.com/developers/applications), create an application, then under
   **Bot** reset and copy the token. No privileged intents are needed.
2. Under **OAuth2 → URL Generator**, tick the `bot` and `applications.commands` scopes and the View Channels, Send
   Messages, Embed Links and Read Message History permissions, and open the URL to add the bot to your server.
3. Make a private channel for reviewers (the posts show every answer) and a reviewer role. With Developer Mode on
   (Discord settings → Advanced), right-click the server, channel and role to copy their ids.
4. Fill in the `DISCORD_*` lines in `.env`, then run the bot from `src/`:

```bash
.venv/bin/pip install -r requirements-bot.txt
set -a && source ../.env && set +a && .venv/bin/python -m rarest_blue.entrypoints.discord_bot
```

The bot only posts and applies changes while it's running. Anyone with the reviewer role, or Manage Server, can
press Apply; the suggester can dismiss their own suggestion.

## Keeping it safe

- `DATABASE_URL` is the master key, and `DISCORD_BOT_TOKEN` lets anyone run the review bot as you. Keep it in `.env` (gitignored) and the host's secret store, never in `web/` or in
  any `NEXT_PUBLIC_*` variable.
- The backend doesn't need the Data API, so you can turn it off in the dashboard's Data API settings. That's a
  second lock on the same door. Run `verify.sh` without the anon key afterwards, since the REST probe needs the API on.
- Free-tier projects pause after about a week without database activity. Daily play keeps the game awake, but
  check your plan's backup policy before you rely on it, since the free tier doesn't include automatic backups.
- `ALTER DEFAULT PRIVILEGES` only covers objects that `postgres` creates. If you add tables or functions some
  other way (dashboard Table Editor, extensions), run `verify.sh` afterwards.
