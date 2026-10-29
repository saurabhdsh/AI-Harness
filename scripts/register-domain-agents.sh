#!/usr/bin/env bash
# Register AD / AMS / QE domain agents via CI upsert (Agent 365–style registry path).
# Prefer catalog sync when the fleet is already listed in examples/catalog.
set -euo pipefail

API="${API_URL:-${HARNESS_API:-http://127.0.0.1:8000}}"
BASE="${DOMAIN_AGENTS_URL:-http://127.0.0.1:8091}"
EMAIL="${HARNESS_EMAIL:-admin@harness.local}"
PASSWORD="${HARNESS_PASSWORD:-harness-admin}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CATALOG="${CATALOG_FILE:-$ROOT/examples/catalog/agents.catalog.json}"

echo "==> Health check $BASE"
curl -sf "$BASE/health" | python3 -m json.tool >/dev/null

echo "==> Login $API"
TOKEN=$(curl -sf -X POST "$API/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

if [[ -f "$CATALOG" ]]; then
  echo "==> Catalog sync from $CATALOG"
  BODY=$(BASE="$BASE" CATALOG="$CATALOG" python3 - <<'PY'
import json, os
with open(os.environ["CATALOG"]) as f:
    body = json.load(f)
body["base_url"] = os.environ["BASE"].rstrip("/")
# Rewrite invoke URLs to current BASE
for a in body.get("agents") or []:
    ext = a.get("external_id")
    if ext:
        a["invoke_url"] = f"{os.environ['BASE'].rstrip('/')}/agents/{ext}/invoke"
print(json.dumps(body))
PY
)
  curl -sf -X POST "$API/api/v1/onboarding/catalog/sync" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d "$BODY" | python3 -m json.tool
  echo "==> Done. Open Agent Registry and invoke with {\"use_sample\": true}."
  exit 0
fi

# Fallback: discover live agents and CI-register each
echo "==> Discover $BASE/agents → CI register"
AGENTS_JSON=$(curl -sf "$BASE/agents")
API="$API" BASE="$BASE" TOKEN="$TOKEN" AGENTS_JSON="$AGENTS_JSON" python3 - <<'PY'
import json, os, urllib.error, urllib.request

api = os.environ["API"]
base = os.environ["BASE"].rstrip("/")
token = os.environ["TOKEN"]
agents = json.loads(os.environ["AGENTS_JSON"])

for a in agents:
    aid = a["id"]
    invoke = a.get("invoke_url") or f"/agents/{aid}/invoke"
    if invoke.startswith("/"):
        invoke = base + invoke
    body = {
        "name": a["name"],
        "external_id": aid,
        "invoke_url": invoke,
        "connector_type": "generic_rest",
        "framework": a.get("framework") or "langgraph",
        "domain": a.get("domain") or "AD",
        "environment": "dev",
        "owner": "domain-agents",
        "team": a.get("domain") or "AD",
        "description": a.get("description") or aid,
        "create_connection": True,
        "metadata": {
            "domain_agent": True,
            "source": "ci",
            "capabilities": a.get("capabilities") or [],
        },
    }
    req = urllib.request.Request(
        f"{api}/api/v1/onboarding/ci/register",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            action = "created" if data.get("created") else "updated"
            print(f"  + {aid} -> {data.get('agent_id')} ({action})")
    except urllib.error.HTTPError as exc:
        err = exc.read().decode()[:200]
        print(f"  ! {aid}: HTTP {exc.code} {err}")
    except Exception as exc:
        print(f"  ! {aid}: {exc}")

print('Done. Open Agent Registry and invoke with {"use_sample": true}.')
PY
