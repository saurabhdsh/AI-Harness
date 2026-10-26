#!/usr/bin/env bash
# Run AI Harness without Docker (Postgres/Redis/Compose not required).
# Uses SQLite for the control plane + local Python/Node processes.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p "$ROOT/data" "$ROOT/data/uploads" "$ROOT/data/logs" "$ROOT/data/pids"

# Load root .env if present (never commit secrets)
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi
if [[ -f "$ROOT/examples/langgraph-openai-agent/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/examples/langgraph-openai-agent/.env"
  set +a
fi

# SQLite — no Postgres
export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///${ROOT}/data/harness.db}"
export AUTH_DEMO="${AUTH_DEMO:-true}"
export AUTO_CREATE_TABLES="${AUTO_CREATE_TABLES:-true}"
export CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:5173,http://127.0.0.1:5173}"
export LANGGRAPH_AGENT_URL="${LANGGRAPH_AGENT_URL:-http://127.0.0.1:8090}"
export HARNESS_PROJECT_ALLOWLIST="${HARNESS_PROJECT_ALLOWLIST:-$ROOT}"
export HTTP_TIMEOUT_SECONDS="${HTTP_TIMEOUT_SECONDS:-90}"
export PYTHONPATH="${ROOT}/services/control-plane${PYTHONPATH:+:$PYTHONPATH}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1"
    exit 1
  }
}

need_cmd python3
need_cmd npm

# LLM: Azure OpenAI preferred when configured (other-Mac style)
if [[ -n "${AZURE_OPENAI_API_KEY:-}" && -n "${AZURE_OPENAI_ENDPOINT:-}" ]]; then
  echo "==> LLM: Azure OpenAI (${AZURE_OPENAI_DEPLOYMENT:-${OPENAI_MODEL:-gpt-5-mini}})"
elif [[ -n "${OPENAI_API_KEY:-}" ]]; then
  echo "==> LLM: OpenAI public API (${OPENAI_MODEL:-gpt-4o-mini})"
else
  echo "==> WARNING: No LLM credentials. Set Azure or OPENAI_API_KEY in .env"
  echo "    Agent invoke / LLM judge will fail until configured."
fi

echo "==> Database: $DATABASE_URL"

# --- venvs / npm ---
if [[ ! -d "$ROOT/services/control-plane/.venv" ]]; then
  echo "==> Creating control-plane venv"
  python3 -m venv "$ROOT/services/control-plane/.venv"
  # shellcheck disable=SC1091
  source "$ROOT/services/control-plane/.venv/bin/activate"
  pip install -q -r "$ROOT/services/control-plane/requirements.txt"
  deactivate
fi

if [[ ! -d "$ROOT/examples/langgraph-openai-agent/.venv" ]]; then
  echo "==> Creating langgraph-openai-agent venv"
  python3 -m venv "$ROOT/examples/langgraph-openai-agent/.venv"
  # shellcheck disable=SC1091
  source "$ROOT/examples/langgraph-openai-agent/.venv/bin/activate"
  pip install -q -r "$ROOT/examples/langgraph-openai-agent/requirements.txt"
  deactivate
fi

if [[ ! -d "$ROOT/apps/mission-control/node_modules" ]]; then
  echo "==> npm install (mission-control)"
  (cd "$ROOT/apps/mission-control" && npm install)
fi

stop_port() {
  local port="$1"
  if lsof -ti:"$port" >/dev/null 2>&1; then
    echo "==> Freeing port $port"
    lsof -ti:"$port" | xargs kill -9 2>/dev/null || true
    sleep 1
  fi
}

stop_port 8000
stop_port 8090
stop_port 5173

echo "==> Starting LangGraph OpenAI agent :8090"
(
  cd "$ROOT/examples/langgraph-openai-agent"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  exec uvicorn main:app --host 127.0.0.1 --port 8090
) >"$ROOT/data/logs/agent.log" 2>&1 &
echo $! >"$ROOT/data/pids/agent.pid"

echo "==> Starting control-plane :8000"
(
  cd "$ROOT/services/control-plane"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  export DATABASE_URL AUTH_DEMO AUTO_CREATE_TABLES CORS_ORIGINS LANGGRAPH_AGENT_URL
  export HARNESS_PROJECT_ALLOWLIST HTTP_TIMEOUT_SECONDS
  export OPENAI_API_KEY OPENAI_MODEL
  export AZURE_OPENAI_API_KEY AZURE_OPENAI_ENDPOINT AZURE_OPENAI_API_VERSION AZURE_OPENAI_DEPLOYMENT
  exec uvicorn app.main:app --host 127.0.0.1 --port 8000
) >"$ROOT/data/logs/api.log" 2>&1 &
echo $! >"$ROOT/data/pids/api.pid"

echo "==> Starting Mission Control UI :5173"
(
  cd "$ROOT/apps/mission-control"
  exec npm run dev -- --host 127.0.0.1 --port 5173
) >"$ROOT/data/logs/ui.log" 2>&1 &
echo $! >"$ROOT/data/pids/ui.pid"

echo "==> Waiting for health…"
ok=0
for i in $(seq 1 40); do
  if curl -sf http://127.0.0.1:8090/health >/dev/null 2>&1 \
    && curl -sf http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 0.5
done
if [[ "$ok" != "1" ]]; then
  echo "WARNING: services may still be starting — check data/logs/"
  tail -n 20 "$ROOT/data/logs/api.log" 2>/dev/null || true
  tail -n 20 "$ROOT/data/logs/agent.log" 2>/dev/null || true
fi

echo ""
echo "AI Harness (no Docker) is up"
echo "  UI:    http://127.0.0.1:5173"
echo "  API:   http://127.0.0.1:8000/docs"
echo "  Agent: http://127.0.0.1:8090/health"
echo "  Login: admin@harness.local / harness-admin"
echo ""
echo "Logs:  $ROOT/data/logs/"
echo "Stop:  $ROOT/scripts/stop-local.sh"
echo ""
echo "Tail logs with: tail -f data/logs/*.log"
