#!/usr/bin/env bash
# Sync a deployed agent catalog into the KEEL registry (Agent 365–style).
# Usage:
#   CATALOG_FILE=examples/catalog/agents.catalog.json ./scripts/catalog-sync.sh
#   Or: BASE_URL=http://127.0.0.1:8091 ./scripts/catalog-sync.sh
set -euo pipefail

API="${HARNESS_API:-${API_URL:-http://127.0.0.1:8000}}"
EMAIL="${HARNESS_EMAIL:-admin@harness.local}"
PASSWORD="${HARNESS_PASSWORD:-harness-admin}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CATALOG="${CATALOG_FILE:-$ROOT/examples/catalog/agents.catalog.json}"
BASE_URL="${BASE_URL:-}"

echo "==> Login $API"
TOKEN=$(curl -sf -X POST "$API/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

if [[ ! -f "$CATALOG" ]]; then
  echo "Catalog file not found: $CATALOG" >&2
  exit 1
fi

BODY=$(CATALOG="$CATALOG" BASE_URL="$BASE_URL" python3 - <<'PY'
import json, os
with open(os.environ["CATALOG"]) as f:
    body = json.load(f)
base = (os.environ.get("BASE_URL") or "").rstrip("/")
if base:
    body["base_url"] = base
    for a in body.get("agents") or []:
        ext = a.get("external_id")
        if ext:
            a["invoke_url"] = f"{base}/agents/{ext}/invoke"
print(json.dumps(body))
PY
)

echo "==> Catalog sync → $API/api/v1/onboarding/catalog/sync"
curl -sf -X POST "$API/api/v1/onboarding/catalog/sync" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "$BODY" | python3 -m json.tool

echo "==> Done"
