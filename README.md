# Rarest Blue

A daily trivia game for UofT students, played as an ocean dive. You get 7 UofT prompts with 20 seconds each.
Any valid answer counts, and **the fewer people who gave your answer, the deeper you sink.**
Each point is 10 m, and the depth zones go from Philosopher's Walk Shallows down to The Steam Tunnels.
Every prompt also hides one **Golden Krill** answer that's worth a +1,000 m bonus.
Pick your college and see how it ranks against the others on the daily standings.

Fan-made. Not affiliated with the University of Toronto.

## Layout

- `src/`: Python (FastAPI + Postgres) backend. It holds answer matching, rarity scoring, leaderboards, and the nightly
  LLM job (via OpenRouter) that writes each day's prompts. The built-in prompt bank is the fallback when generation fails.
  It's layered so that imports only point inward (`tests/unit/test_architecture.py` enforces this):
  - `domain/`: game rules and entities in pure Python (matching, scoring, zones, the prompt bank)
  - `application/`: use cases (play a day, generate a set, review guesses) and the ports they need
  - `infrastructure/`: adapters for those ports (Postgres/Supabase, OpenRouter)
  - `entrypoints/`: the HTTP API and the CLI jobs, which wire it all together
- `supabase/`: the production database migration (locked away from Supabase's public APIs) and a verify script.
- `deploy/`, `.github/`: Cloud Run manifests, one-time GCP setup, and CI/CD. See `deploy/README.md`.
- `web/`: Next.js frontend. It proxies `/api/*` to the backend.

## Quickstart (Docker)

```bash
cp .env.example .env          # then paste your OpenRouter key into .env
docker compose up --build     # Postgres + API on http://localhost:8000

# frontend (another terminal)
cd web && npm install && npm run dev   # http://localhost:3000
```

Generate tomorrow's prompts into the local database: `docker compose run --rm api python -m rarest_blue.entrypoints.cli.generate`.
Add `--dry-run` to print the set without storing it. `docker compose down -v` wipes the database.

## Run it without Docker

```bash
# needs a Postgres matching the default DATABASE_URL, e.g. `docker compose up -d db`

# backend (terminal 1)
cd src
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn --factory rarest_blue.entrypoints.http.app:create_app --reload --port 8000

# frontend (terminal 2)
cd web
npm install
npm run dev        # http://localhost:3000
```

Tests: `cd src && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest && .venv/bin/ruff check .`.
The API and generator tests need a scratch Postgres: set `TEST_DATABASE_URL` (its tables get truncated). Without it they're skipped.
Don't point it at your dev database. With compose, run `docker compose exec db createdb -U postgres rarest_test` once and use
`TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/rarest_test`.

## Daily prompts

Each night at 23:30 Toronto time, `python -m rarest_blue.entrypoints.cli.generate` asks an LLM on OpenRouter for tomorrow's 7 prompts.
It checks them (enough answers, no colliding aliases, a real deep-cut golden answer, decoys that don't accidentally
match a real answer), retries up to 3 times (cycling through `OPENROUTER_MODELS`), and
stores the set in the `daily_prompts` table. At midnight the API serves the new day's row. Nothing gets redeployed.

If a day has no stored set when its first request arrives, the API stores and serves a set from the built-in bank in
`domain/prompt_bank.py`. The day's set never changes once it's been served, except through the review tool below.

Try it without storing anything: `OPENROUTER_API_KEY=... .venv/bin/python -m rarest_blue.entrypoints.cli.generate --dry-run`.
Use `--day YYYY-MM-DD` to generate a specific day.

Each prompt in `/api/daily` has a `suggestions` list for the answer box's autocomplete. It holds every right answer
plus the generated decoys (plausible wrong answers), sorted alphabetically, so the dropdown doesn't give the answers
away. The built-in fallback prompts have hand-written decoys.

## Reviewing rejected guesses

A real answer missing from the list scores zero, so check what players typed that got rejected:

```bash
docker compose run --rm api python -m rarest_blue.entrypoints.cli.review                      # today's top rejected guesses
docker compose run --rm api python -m rarest_blue.entrypoints.cli.review accept subway "Dupont"                # add a new answer
docker compose run --rm api python -m rarest_blue.entrypoints.cli.review accept subway "Spadina Stn" --as Spadina  # add an alias
```

Accepting updates the day's stored set and rescores every guess it now matches, leaderboard totals included.
Pass `--day YYYY-MM-DD` before the subcommand for another day.

## Adding fallback prompts

Edit `src/rarest_blue/domain/prompt_bank.py`. List the answers from most to least obvious, because list
order seeds the starting popularity. Set `golden` to that prompt's hidden bonus answer. Put the canonical name first in each tuple and its aliases after it.
`tests/unit/test_matching.py` and `tests/unit/test_prompt_bank.py` catch colliding aliases, scoring decoys and
obvious golden answers.

## Config

- `API_URL` (web): sets the backend URL. The default is `http://localhost:8000`.
- `DATABASE_URL` (src): the Postgres connection string. For Supabase, use the **transaction pooler** URL.
- `OPENROUTER_API_KEY` (src, generator only): the OpenRouter API key.
- `OPENROUTER_MODELS` (src, generator only): comma-separated models to try in order. The default is three free
  models, led by `particle-ai/particle-1:free`. To switch to a paid model later, set something like `google/gemini-...`.
- `CORS_ORIGINS` (src): a comma-separated list of allowed origins.

## Deploy (Cloud Run + Supabase)

The `src/Dockerfile` image runs both the API (a Cloud Run service) and the nightly generator (a Cloud Run job that
Cloud Scheduler triggers at 23:30 Toronto time). Run `deploy/setup.sh` once per GCP project. After that, every merge
to `main` that touches the backend is tested, built, deployed and smoke-tested by GitHub Actions, with no stored keys.
See `deploy/README.md` for the setup and the security model, and `supabase/README.md` for the database.
