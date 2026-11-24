# Deploying the backend (Cloud Run)

One container image (`src/Dockerfile`) runs in two places:

| What | Cloud Run resource | Runs as | Secrets it can read |
|---|---|---|---|
| The API (`uvicorn --factory rarest_blue.entrypoints.http.app:create_app`) | service `rarest-blue-api` | `rarest-blue-api` SA | `rarest-blue-database-url` |
| Tomorrow's prompts (`python -m rarest_blue.entrypoints.cli.generate`) | job `rarest-blue-generate`, run by Cloud Scheduler at 23:30 Toronto | `rarest-blue-generator` SA | `rarest-blue-database-url`, `rarest-blue-openrouter-key` |

The database is Supabase (see `supabase/README.md`). The frontend's Next.js server proxies `/api/*` to the service URL,
so set the frontend's `API_URL` to it.

## First-time setup

You need `gcloud` logged in as a project owner and `gh` (or `GITHUB_REPO_ID`).

```bash
PROJECT_ID=<your-project> deploy/setup.sh
```

The script is idempotent. It:
- enables the APIs;
- creates the Artifact Registry repo, the service accounts and the secrets. It prompts for the secret values with
  hidden input, so they never touch disk, shell history or `ps`;
- sets up Workload Identity Federation for GitHub;
- creates a placeholder service and job, and the nightly schedule.

At the end it prints five values, `CORS_ORIGINS` included. Add them as GitHub **repository variables** (they
aren't secrets). Also apply the Supabase migration once (`supabase/README.md`).

## CI/CD

- **`backend-ci.yml`** is one job, run on PRs that touch the backend. It:
  - applies the Supabase migration twice to a Postgres set up with Supabase's API roles;
  - runs `pytest`;
  - re-checks the lockdown with `supabase/verify.sh`;
  - runs `ruff` lint and format checks, including the architecture test that keeps layers pointing inward;
  - runs `pip-audit` on the full hash-locked dependency set (`src/requirements.lock`);
  - builds the image and runs `deploy/smoke-image.sh`: non-root, serves 7 prompts, no answer keys in the payload,
    no `/docs`;
  - checks the Cloud Run manifests render with no unfilled variables.
- **`backend-deploy.yml`** runs on merge to `main`. It runs CI again, then:
  - builds the image and smoke-tests that exact image;
  - only then gets a GCP token, pushes it, and deploys the service and the job **by that digest**;
  - smoke-tests production `/api/daily`.

  For a manual approval gate, add required reviewers to the `production` environment in GitHub, and restrict the
  environment to the `main` branch. The token condition requires that environment, so the gate can't be skipped.

## Security model

- **No stored GCP keys.** GitHub's OIDC token is exchanged for a short-lived token. The provider only accepts tokens
  from `backend-deploy.yml` on `main`, in the `production` environment, of this repository. The repository is
  matched by numeric id, so a renamed or recreated repo can't take over. PRs, forks, other branches and other
  workflows can't get a token.
- **Least privilege:**
  - The deployer has `run.developer` on just the API service and the generator job, not project-wide. It can
    write to the one image repo and act as the two runtime accounts, and it can't change IAM. It can't read
    secrets directly, but code it deploys runs with those secrets. So the real trust boundary is "who can merge to
    `main`": protect that branch.
  - Each runtime account reads only its own secrets.
  - The scheduler account can only run the generator job.
- **Secrets** live in Secret Manager and are mounted as env vars at runtime. They aren't in the image, the repo
  or GitHub.
- **Supply chain:**
  - Every action is pinned to a commit SHA, the base image to a digest, and every Python package (transitive
    ones included) to a version and hash in `requirements.lock`. Nothing updates itself, so nothing opens PRs on its
    own. To bump Python deps, edit `src/requirements.txt` and rerun the `uv pip compile` line at its top. CI's
    `pip-audit` fails when a pinned package gets a known vulnerability, which tells you when to bump.
  - Only GitHub's and Google's own actions are used.
  - Artifact Registry scans each pushed image for vulnerabilities.
- **Container:** runs as uid 10001 with code it can't modify. Requests time out at 30 s. The API docs and OpenAPI
  schema are switched off, CORS allows only `GET`/`POST` with `Content-Type`, and `X-Forwarded-For` isn't trusted.
  Cloud Run's request logs record the real client IP.
- **Scaling and cost:** 0 to 4 instances, 40 concurrent requests each. That caps cost and the number of Supabase
  pooler connections.
- **Public by design:** the service allows unauthenticated calls, because the Next.js server calls it without
  credentials. Abuse limits (rate limiting, authenticated player ids) belong in the app.

## Operating

```bash
# run tomorrow's generation now
gcloud run jobs execute rarest-blue-generate --region $REGION --wait
# logs
gcloud run services logs read rarest-blue-api --region $REGION --limit 100
# roll back to the previous revision
gcloud run revisions list --service rarest-blue-api --region $REGION
gcloud run services update-traffic rarest-blue-api --region $REGION --to-revisions <revision>=100
# rotate a secret (new revisions pick up :latest; redeploy or roll a new revision to apply)
gcloud secrets versions add rarest-blue-database-url --data-file=-
```
