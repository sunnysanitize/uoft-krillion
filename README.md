# Rarest Blue

A daily trivia game for UofT students, played as an ocean dive. You get 7 UofT prompts with 20 seconds each.
Any valid answer counts, and **the fewer people who gave your answer, the deeper you sink.**
Each point is 10 m, and the depth zones go from Philosopher's Walk Shallows down to The Steam Tunnels.
Every prompt also hides one **Golden Krill** answer that's worth a +1,000 m bonus.
Pick your college and see how it ranks against the others on the daily standings.

Fan-made. Not affiliated with the University of Toronto.

## Layout

- `src/`: Python (FastAPI + SQLite) backend. It holds the prompt bank, answer matching, rarity scoring, and leaderboards.
- `web/`: Next.js frontend. It proxies `/api/*` to the backend.

## Run it

```bash
# backend (terminal 1)
cd src
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn rarest_blue.api:app --reload --port 8000

# frontend (terminal 2)
cd web
npm install
npm run dev        # http://localhost:3000
```

Tests: `cd src && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest`

## Adding prompts

Edit `src/rarest_blue/prompts.py`. List the answers from most to least obvious, because list
order seeds the starting popularity. Set `golden` to that prompt's hidden bonus answer. Put the canonical name first in each tuple and its aliases after it.
`tests/test_game.py` catches aliases that collide.

## Config

- `API_URL` (web): sets the backend URL. The default is `http://localhost:8000`.
- `RAREST_BLUE_DB` (src): sets the SQLite file path.
- `CORS_ORIGINS` (src): a comma-separated list of allowed origins.
