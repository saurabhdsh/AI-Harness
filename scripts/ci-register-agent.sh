#!/usr/bin/env bash
# Post-deploy: register (or update) an agent in Harness from CI/CD.
# Usage:
#   HARNESS_API=http://127.0.0.1:8000 \
#   HARNESS_EMAIL=admin@harness.local HARNESS_PASSWORD=harness-admin \
#   EXTERNAL_ID=ad-user-story \
#   INVOKE_URL=http://127.0.0.1:8091/agents/ad-user-story/invoke \
#   GIT_REPO=https://github.com/org/agents GIT_SHA=$(git rev-parse HEAD) \
#   ./scripts/ci-register-agent.sh
set -euo pipefail

API="${HARNESS_API:-http://127.0.0.1:8000}"
EMAIL="${HARNESS_EMAIL:-admin@harness.local}"
PASSWORD="${HARNESS_PASSWORD:-harness-admin}"

: "${EXTERNAL_ID:?EXTERNAL_ID required}"
: "${INVOKE_URL:?INVOKE_URL required}"

NAME="${NAME:-$EXTERNAL_ID}"
DOMAIN="${DOMAIN:-AD}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
CONNECTOR="${CONNECTOR_TYPE:-generic_rest}"
GIT_REPO="${GIT_REPO:-}"
GIT_REF="${GIT_REF:-}"
GIT_SHA="${GIT_SHA:-}"
PIPELINE_ID="${PIPELINE_ID:-${GITHUB_RUN_ID:-${BUILD_BUILDID:-}}}"
PIPELINE_URL="${PIPELINE_URL:-}"

echo "==> Login $API"
TOKEN=$(curl -sf -X POST "$API/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

BODY=$(EXTERNAL_ID="$EXTERNAL_ID" INVOKE_URL="$INVOKE_URL" NAME="$NAME" \
  DOMAIN="$DOMAIN" ENVIRONMENT="$ENVIRONMENT" CONNECTOR="$CONNECTOR" \
  GIT_REPO="$GIT_REPO" GIT_REF="$GIT_REF" GIT_SHA="$GIT_SHA" \
  PIPELINE_ID="$PIPELINE_ID" PIPELINE_URL="$PIPELINE_URL" python3 - <<'PY'
import json, os
print(json.dumps({
  "name": os.environ["NAME"],
  "external_id": os.environ["EXTERNAL_ID"],
  "invoke_url": os.environ["INVOKE_URL"],
  "connector_type": os.environ["CONNECTOR"],
  "framework": os.environ["CONNECTOR"],
  "domain": os.environ["DOMAIN"],
  "environment": os.environ["ENVIRONMENT"],
  "git_repo": os.environ.get("GIT_REPO") or None,
  "git_ref": os.environ.get("GIT_REF") or None,
  "git_sha": os.environ.get("GIT_SHA") or None,
  "pipeline_id": os.environ.get("PIPELINE_ID") or None,
  "pipeline_url": os.environ.get("PIPELINE_URL") or None,
  "create_connection": True,
}))
PY
)

echo "==> CI register $EXTERNAL_ID → $INVOKE_URL"
curl -sf -X POST "$API/api/v1/onboarding/ci/register" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "$BODY" | python3 -m json.tool

echo "==> Done"
