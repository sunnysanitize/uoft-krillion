#!/usr/bin/env bash
# Smoke-tests a built image: it runs as non-root, starts and preloads a playable full day.
#
#   deploy/smoke-image.sh <image> <database-url>
#
# Used by CI and by the deploy job, which runs it on the exact image it then pushes.
set -euo pipefail

image=${1:?image}
db=${2:?database url}
name=rarest-blue-smoke

uid=$(docker run --rm --entrypoint id "$image" -u)
[ "$uid" != 0 ] || { echo "image runs as root"; exit 1; }

docker rm -f "$name" >/dev/null 2>&1 || true
docker run -d --name "$name" --network host -e PORT=8080 -e DATABASE_URL="$db" "$image" >/dev/null
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT

for _ in $(seq 1 30); do
  curl -sf -o /dev/null localhost:8080/api/daily && break
  sleep 1
done

body=$(curl -sf localhost:8080/api/daily) || { echo "app never served /api/daily"; docker logs "$name" | tail -20; exit 1; }
python3 - "$body" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
assert len(d["prompts"]) == 7, "expected 7 prompts"
for p in d["prompts"]:
    assert set(p) == {"id", "text", "hint", "play"}, f"unexpected keys in prompt: {sorted(p)}"
    assert p["play"]["answers"], "missing preloaded matching data"
    assert p["play"]["golden_answer"], "missing preloaded bonus answer"
print("smoke ok: 7 prompts with preloaded matching and scores")
PY

code=$(curl -s -o /dev/null -w '%{http_code}' localhost:8080/docs)
[ "$code" = 404 ] || { echo "/docs is exposed ($code)"; exit 1; }
