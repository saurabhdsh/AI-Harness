#!/usr/bin/env bash
# Register AD / AMS / QE domain agents into a running control plane.
set -euo pipefail

API="${API_URL:-http://127.0.0.1:8000}"
BASE="${DOMAIN_AGENTS_URL:-http://127.0.0.1:8091}"

echo "==> Health check $BASE"
curl -sf "$BASE/health" | python3 -m json.tool >/dev/null

echo "==> Login $API"
TOKEN=$(curl -sf -X POST "$API/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@harness.local","password":"harness-admin"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

AGENTS_JSON=$(curl -sf "$BASE/agents")
COUNT=$(echo "$AGENTS_JSON" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))')
echo "==> Discovered $COUNT agents — registering"

API="$API" BASE="$BASE" TOKEN="$TOKEN" AGENTS_JSON="$AGENTS_JSON" python3 - <<'PY'
import json, os, urllib.error, urllib.request

api = os.environ["API"]
base = os.environ["BASE"]
token = os.environ["TOKEN"]
agents = json.loads(os.environ["AGENTS_JSON"])

for a in agents:
    aid = a["id"]
    invoke = a.get("invoke_url") or f"/agents/{aid}/invoke"
    if invoke.startswith("/"):
        invoke = base.rstrip("/") + invoke
    body = {
        "name": a["name"],
        "platform": "local",
        "framework": a.get("framework") or "langgraph",
        "external_id": aid,
        "domain": a.get("domain") or "AD",
        "environment": "dev",
        "lifecycle_state": "registered",
        "owner": "domain-agents",
        "team": a.get("domain") or "AD",
        "invoke_url": invoke,
        "description": a.get("description") or aid,
        "metadata": {
            "domain_agent": True,
            "agent_id": aid,
            "capabilities": a.get("capabilities") or [],
        },
    }
    req = urllib.request.Request(
        f"{api}/api/v1/agents",
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
            print(f"  + {aid} -> {data.get('id')} ({data.get('name')})")
    except urllib.error.HTTPError as exc:
        err = exc.read().decode()[:200]
        print(f"  ! {aid}: HTTP {exc.code} {err}")
    except Exception as exc:
        print(f"  ! {aid}: {exc}")

print('Done. Open Agent Universe and invoke with {"use_sample": true}.')
PY
