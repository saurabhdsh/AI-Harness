#!/usr/bin/env bash
set -euo pipefail

API="${API_URL:-http://127.0.0.1:8000}"
AGENT="${LANGGRAPH_URL:-http://127.0.0.1:8080}"

echo "==> Health checks"
curl -sf "$AGENT/health" | head -c 200; echo
curl -sf "$API/api/v1/health" | head -c 200; echo

echo "==> Login"
TOKEN=$(curl -sf -X POST "$API/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@harness.local","password":"harness-admin"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
AUTH="Authorization: Bearer $TOKEN"

echo "==> List agents"
AGENTS=$(curl -sf "$API/api/v1/agents" -H "$AUTH")
echo "$AGENTS" | python3 -c 'import sys,json; a=json.load(sys.stdin); assert len(a)>=1, "no agents"; print(f"{len(a)} agent(s):", a[0]["name"])'
AGENT_ID=$(echo "$AGENTS" | python3 -c 'import sys,json; print(json.load(sys.stdin)[0]["id"])')

echo "==> Invoke agent $AGENT_ID"
INVOKE=$(curl -sf -X POST "$API/api/v1/agents/$AGENT_ID/invoke" \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"input":{"task":"improve","use_sample":true}}')
echo "$INVOKE" | python3 -c 'import sys,json; r=json.load(sys.stdin); assert r["status"]=="succeeded", r; print("latency_ms=", r.get("latency_ms"), "execution=", r["execution_id"])'
EXEC_ID=$(echo "$INVOKE" | python3 -c 'import sys,json; print(json.load(sys.stdin)["execution_id"])')

echo "==> Fetch trace by execution id"
curl -sf "$API/api/v1/traces/$EXEC_ID" -H "$AUTH" \
  | python3 -c 'import sys,json; t=json.load(sys.stdin); assert t.get("spans"), t; print("spans=", len(t["spans"]))'

echo "==> Run evaluation"
EVAL=$(curl -sf -X POST "$API/api/v1/evaluations" \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"agent_id\":\"$AGENT_ID\",\"name\":\"smoke-suite\",\"cases\":[{\"case_id\":\"c1\",\"input\":{\"task\":\"analyze\",\"use_sample\":true},\"expected\":{\"issues\":[]},\"match_mode\":\"keys\"}],\"use_llm_judge\":false}")
echo "$EVAL" | python3 -c 'import sys,json; r=json.load(sys.stdin); print("eval status=", r.get("status"), "score=", r.get("aggregate_score"))'

echo "==> Mission overview"
curl -sf "$API/api/v1/mission/overview" -H "$AUTH" \
  | python3 -c 'import sys,json; o=json.load(sys.stdin); print("agents=", o["total_agents"], "exec_24h=", o["recent_executions"])'

echo "SMOKE OK"
