#!/usr/bin/env bash
# One-time GCP bootstrap for the Rarest Blue backend on Cloud Run. Safe to re-run: it creates what's
# missing and leaves the rest alone.
#
#   PROJECT_ID=my-project deploy/setup.sh
#
# Optional: REGION (default northamerica-northeast2, Toronto), GITHUB_REPO (default sunnysanitize/uoft-krillion),
# DEPLOY_BRANCH (default main).
#
# It sets up:
#   * Artifact Registry repo `rarest-blue` (with vulnerability scanning on)
#   * four service accounts, each with only what it needs:
#       rarest-blue-api        runtime of the API; reads the DATABASE_URL secret
#       rarest-blue-generator  runtime of the nightly job; reads DATABASE_URL + the OpenRouter key
#       rarest-blue-scheduler  Cloud Scheduler identity; may only run the generator job
#       rarest-blue-deployer   GitHub Actions identity; pushes images and deploys, nothing else
#   * Secret Manager secrets (it prompts for their values; they never touch disk or argv)
#   * Workload Identity Federation, so GitHub Actions gets short-lived tokens with no stored key,
#     and only from this repo's DEPLOY_BRANCH
#   * placeholder service + job (so IAM can be attached before the first real deploy) and the nightly schedule
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
REGION=${REGION:-northamerica-northeast2}
GITHUB_REPO=${GITHUB_REPO:-sunnysanitize/uoft-krillion}
DEPLOY_BRANCH=${DEPLOY_BRANCH:-main}

AR_REPO=rarest-blue
SERVICE=rarest-blue-api
JOB=rarest-blue-generate
SCHEDULE_NAME=rarest-blue-generate-nightly
POOL=github
PROVIDER=github-actions
PLACEHOLDER=us-docker.pkg.dev/cloudrun/container/hello

g() { gcloud --project "$PROJECT_ID" --quiet "$@"; }
# IAM on a just-created account or API can lag by a few seconds; retry instead of failing a first run.
retry() { local i; for i in 1 2 3 4 5 6; do "$@" && return 0; echo "  (retrying in $((i * 5))s)"; sleep $((i * 5)); done; "$@"; }
sa() { echo "rarest-blue-$1@$PROJECT_ID.iam.gserviceaccount.com"; }
step() { printf '\n== %s\n' "$1"; }

PROJECT_NUMBER=$(g projects describe "$PROJECT_ID" --format='value(projectNumber)')

if command -v gh >/dev/null; then
  GITHUB_REPO_ID=${GITHUB_REPO_ID:-$(gh api "repos/$GITHUB_REPO" --jq .id)}
fi
: "${GITHUB_REPO_ID:?set GITHUB_REPO_ID (numeric id from https://api.github.com/repos/$GITHUB_REPO), or install gh}"

step "APIs"
g services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com \
  iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com cloudscheduler.googleapis.com \
  containerscanning.googleapis.com

step "Artifact Registry"
g artifacts repositories describe "$AR_REPO" --location "$REGION" >/dev/null 2>&1 ||
  g artifacts repositories create "$AR_REPO" --location "$REGION" --repository-format docker \
    --description "Rarest Blue backend images"

step "Service accounts"
for name in api generator scheduler deployer; do
  g iam service-accounts describe "$(sa "$name")" >/dev/null 2>&1 ||
    g iam service-accounts create "rarest-blue-$name" --display-name "Rarest Blue $name"
done

step "Secrets"
add_secret() {  # name, prompt
  g secrets describe "$1" >/dev/null 2>&1 || g secrets create "$1" --replication-policy automatic
  if [ -z "$(g secrets versions list "$1" --filter 'state=ENABLED' --limit 1 --format 'value(name)')" ]; then
    printf '%s (input hidden): ' "$2"; IFS= read -rs value; echo
    # Required: the service and job reference :latest, so a missing version would break the first deploy.
    [ -n "$value" ] || { echo "$1 needs a value"; exit 1; }
    printf '%s' "$value" | g secrets versions add "$1" --data-file=-
    unset value
  else
    echo "$1 already has a value (add a new version with: gcloud secrets versions add $1 --data-file=-)"
  fi
}
add_secret rarest-blue-database-url "Supabase DATABASE_URL (transaction pooler URI with sslmode=require)"
add_secret rarest-blue-openrouter-key "OPENROUTER_API_KEY"

grant_secret() { retry g secrets add-iam-policy-binding "$1" --member "serviceAccount:$2" \
  --role roles/secretmanager.secretAccessor --condition None >/dev/null; }
grant_secret rarest-blue-database-url "$(sa api)"
grant_secret rarest-blue-database-url "$(sa generator)"
grant_secret rarest-blue-openrouter-key "$(sa generator)"

step "Workload Identity Federation (GitHub Actions, $GITHUB_REPO@$DEPLOY_BRANCH only)"
g iam workload-identity-pools describe "$POOL" --location global >/dev/null 2>&1 ||
  g iam workload-identity-pools create "$POOL" --location global --display-name "GitHub Actions"
# Only the deploy workflow, on the deploy branch, in the `production` environment, of this exact repo (numeric
# id, so a new repo with the same name can't claim it; after a rename, re-run this script). PRs, forks, other branches and other
# workflows can never get a token, and the environment's protection rules can't be skipped.
# Keep this pool dedicated to this one provider: the IAM binding below trusts the whole pool.
DEPLOY_WORKFLOW="$GITHUB_REPO/.github/workflows/backend-deploy.yml@refs/heads/$DEPLOY_BRANCH"
CONDITION="assertion.repository_id == '$GITHUB_REPO_ID' && assertion.ref == 'refs/heads/$DEPLOY_BRANCH' \
&& assertion.workflow_ref == '$DEPLOY_WORKFLOW' && assertion.environment == 'production'"
if g iam workload-identity-pools providers describe "$PROVIDER" --location global --workload-identity-pool "$POOL" >/dev/null 2>&1; then
  g iam workload-identity-pools providers update-oidc "$PROVIDER" --location global --workload-identity-pool "$POOL" \
    --attribute-condition "$CONDITION" >/dev/null
else
  g iam workload-identity-pools providers create-oidc "$PROVIDER" --location global --workload-identity-pool "$POOL" \
    --issuer-uri https://token.actions.githubusercontent.com \
    --attribute-mapping 'google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.ref=assertion.ref' \
    --attribute-condition "$CONDITION"
fi
POOL_ID="projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL"
retry g iam service-accounts add-iam-policy-binding "$(sa deployer)" --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/$POOL_ID/attribute.repository_id/$GITHUB_REPO_ID" >/dev/null

step "Deployer permissions"
retry g artifacts repositories add-iam-policy-binding "$AR_REPO" --location "$REGION" \
  --member "serviceAccount:$(sa deployer)" --role roles/artifactregistry.writer >/dev/null
# Deploying a revision that runs as a service account needs actAs on that account, and only those two.
for runtime in api generator; do
  retry g iam service-accounts add-iam-policy-binding "$(sa "$runtime")" --member "serviceAccount:$(sa deployer)" \
    --role roles/iam.serviceAccountUser >/dev/null
done

step "Placeholder service and job"
g run services describe "$SERVICE" --region "$REGION" >/dev/null 2>&1 ||
  g run deploy "$SERVICE" --region "$REGION" --image "$PLACEHOLDER" --service-account "$(sa api)" \
    --no-allow-unauthenticated
g run jobs describe "$JOB" --region "$REGION" >/dev/null 2>&1 ||
  g run jobs create "$JOB" --region "$REGION" --image "$PLACEHOLDER" --service-account "$(sa generator)"

# The Next.js server calls the API without credentials, so the service is public. The data stays safe because
# the API only exposes the game endpoints; Supabase itself is locked down (supabase/README.md).
g run services add-iam-policy-binding "$SERVICE" --region "$REGION" --member allUsers --role roles/run.invoker >/dev/null
g run jobs add-iam-policy-binding "$JOB" --region "$REGION" --member "serviceAccount:$(sa scheduler)" \
  --role roles/run.invoker >/dev/null
# The deployer may update these two resources and nothing else in the project (no project-level Cloud Run role).
g run services add-iam-policy-binding "$SERVICE" --region "$REGION" --member "serviceAccount:$(sa deployer)" \
  --role roles/run.developer >/dev/null
g run jobs add-iam-policy-binding "$JOB" --region "$REGION" --member "serviceAccount:$(sa deployer)" \
  --role roles/run.developer >/dev/null

step "Nightly schedule (23:30 America/Toronto)"
SCHEDULER_REGION=${SCHEDULER_REGION:-$REGION}
RUN_URI="https://run.googleapis.com/v2/projects/$PROJECT_ID/locations/$REGION/jobs/$JOB:run"
if g scheduler jobs describe "$SCHEDULE_NAME" --location "$SCHEDULER_REGION" >/dev/null 2>&1; then verb=update; else verb=create; fi
g scheduler jobs "$verb" http "$SCHEDULE_NAME" --location "$SCHEDULER_REGION" \
  --schedule "30 23 * * *" --time-zone America/Toronto --uri "$RUN_URI" --http-method POST \
  --oauth-service-account-email "$(sa scheduler)" --attempt-deadline 60s >/dev/null

cat <<EOF

Done. Add these as GitHub repository *variables* (Settings > Secrets and variables > Actions > Variables).
None of them are secret:

  GCP_PROJECT_ID     $PROJECT_ID
  GCP_REGION         $REGION
  GCP_WIF_PROVIDER   $POOL_ID/providers/$PROVIDER
  GCP_DEPLOYER_SA    $(sa deployer)
  CORS_ORIGINS       https://<your frontend origin>

Then merge to $DEPLOY_BRANCH (or run the "Backend deploy" workflow) to ship the real image.
Point the frontend's API_URL at: $(g run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')
EOF
