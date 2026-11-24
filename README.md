# UofT Krillion

A daily trivia game for UofT students, played as an ocean dive. You get 7 UofT prompts with 25 seconds each.
Any valid answer counts, and **the fewer people who gave your answer, the deeper you sink.**
Each point is 10 m, and the depth zones go from Philosopher's Walk Shallows down to The Steam Tunnels.
Answers score by rarity: Common 10, Uncommon 30, Rare 60, Deep Cut 85. Every prompt also hides one
**One in a Krillion** answer worth 100.
See how deep you went against everyone else on the daily standings.

Fan-made. Not affiliated with the University of Toronto.

## Layout

- `src/`: Python (FastAPI + Postgres) backend. It holds answer matching, rarity scoring, leaderboards, and the nightly
  LLM job (via OpenRouter) that writes each day's prompts. The built-in prompt bank is the fallback when generation fails.
- `web/`: Next.js frontend. It proxies `/api/*` to the backend.

## Quickstart (Docker)

```bash
cp .env.example .env          # then paste your OpenRouter key into .env
docker compose up --build     # Postgres + API on http://localhost:8000

# frontend (another terminal)
cd web && npm install && npm run dev   # http://localhost:3000
```

Generate tomorrow's prompts into the local database: `docker compose run --rm api python -m rarest_blue.generate`.
Add `--dry-run` to print the set without storing it. `docker compose down -v` wipes the database.

## Run it without Docker

```bash
# needs a Postgres matching the default DATABASE_URL, e.g. `docker compose up -d db`

# backend (terminal 1)
cd src
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn rarest_blue.api:app --reload --port 8000

# frontend (terminal 2)
cd web
npm install
npm run dev        # http://localhost:3000
```

Tests: `cd src && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest`.
The API and generator tests need a scratch Postgres: set `TEST_DATABASE_URL` (its tables get truncated). Without it they're skipped.
Don't point it at your dev database. With compose, run `docker compose exec db createdb -U postgres rarest_test` once and use
`TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/rarest_test`.

## Daily prompts

Each night at 23:30 Toronto time, `python -m rarest_blue.generate` asks an LLM on OpenRouter for tomorrow's 7 prompts.
It checks them (enough answers, no colliding aliases, a real deep-cut golden answer, decoys that don't accidentally
match a real answer), retries up to 3 times (cycling through `OPENROUTER_MODELS`), and
stores the set in the `daily_prompts` table. At midnight the API serves the new day's row. Nothing gets redeployed.

If a day has no stored set when its first request arrives, the API stores and serves a set from the built-in bank in
`prompts.py`. The day's set never changes once it's been served, except through the review tool below.

Try it without storing anything: `OPENROUTER_API_KEY=... .venv/bin/python -m rarest_blue.generate --dry-run`.
Use `--day YYYY-MM-DD` to generate a specific day.

Each prompt in `/api/daily` has a `suggestions` list for the answer box's autocomplete. It holds every right answer
plus the generated decoys (plausible wrong answers), sorted alphabetically, so the dropdown doesn't give the answers
away. The built-in fallback prompts have hand-written decoys.

## Reviewing rejected guesses

A real answer missing from the list scores zero, so check what players typed that got rejected:

```bash
docker compose run --rm api python -m rarest_blue.review                      # today's top rejected guesses
docker compose run --rm api python -m rarest_blue.review accept subway "Dupont"                # add a new answer
docker compose run --rm api python -m rarest_blue.review accept subway "Spadina Stn" --as Spadina  # add an alias
```

Accepting updates the day's stored set and rescores every guess it now matches, leaderboard totals included.
Pass `--day YYYY-MM-DD` before the subcommand for another day.

## Adding fallback prompts

Edit `src/rarest_blue/prompts.py`. List the answers from most to least obvious, because list
order seeds the starting popularity. Set `golden` to that prompt's hidden bonus answer. Put the canonical name first in each tuple and its aliases after it.
`tests/test_game.py` catches aliases that collide.

## Config

- `API_URL` (web): sets the backend URL. The default is `http://localhost:8000`.
- `DATABASE_URL` (src): the Postgres connection string. For Supabase, use the **transaction pooler** URL.
- `OPENROUTER_API_KEY` (src, generator only): the OpenRouter API key.
- `OPENROUTER_MODELS` (src, generator only): comma-separated models to try in order. The default is three free
  models, led by `particle-ai/particle-1:free`. To switch to a paid model later, set something like `google/gemini-...`.
- `CORS_ORIGINS` (src): a comma-separated list of allowed origins.

## Deploy (Cloud Run + Supabase)

The `src/Dockerfile` image runs both the API service and the generator job.

```bash
PROJECT=your-gcp-project REGION=us-east1
IMAGE=$REGION-docker.pkg.dev/$PROJECT/rarest-blue/backend

# one-time setup
gcloud artifacts repositories create rarest-blue --repository-format docker --location $REGION
printf '%s' 'postgresql://...pooler.supabase.com:6543/postgres' | gcloud secrets create database-url --data-file=-
printf '%s' 'your-openrouter-key' | gcloud secrets create openrouter-api-key --data-file=-

# build, then deploy the API
gcloud builds submit src --tag $IMAGE
gcloud run deploy rarest-blue-api --image $IMAGE --region $REGION --allow-unauthenticated \
  --set-secrets DATABASE_URL=database-url:latest --set-env-vars CORS_ORIGINS=https://your-frontend.example

# the nightly job
gcloud run jobs create rarest-blue-generate --image $IMAGE --region $REGION \
  --command python --args=-m,rarest_blue.generate --max-retries 1 --task-timeout 25m \
  --set-secrets DATABASE_URL=database-url:latest,OPENROUTER_API_KEY=openrouter-api-key:latest
```

Schedule the job from the Cloud Run console: open **rarest-blue-generate**, go to **Triggers**, add a scheduler
trigger with cron `30 23 * * *` and time zone `America/Toronto`. After a code change, rebuild the image and run
`gcloud run deploy` and `gcloud run jobs update rarest-blue-generate --image $IMAGE --region $REGION`.
