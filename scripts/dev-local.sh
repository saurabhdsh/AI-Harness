#!/usr/bin/env bash
# Run AI Harness without Docker (Postgres/Redis/Compose not required).
# Uses SQLite for the control plane + local Python/Node processes.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p "$ROOT/data" "$ROOT/data/uploads" "$ROOT/data/logs" "$ROOT/data/pids"

# Safe .env loader — never `source` (breaks on blank lines / Windows CRLF / comments)
load_env_file() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  local line key val
  while IFS= read -r line || [[ -n "$line" ]]; do
    # strip CR from Windows-edited .env files
    line="${line%$'\r'}"
    # skip blanks and comments
    [[ -z "${line//[[:space:]]/}" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    # only KEY=VALUE
    if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      key="${BASH_REMATCH[1]}"
      val="${BASH_REMATCH[2]}"
      # strip optional surrounding quotes
      if [[ "$val" =~ ^\"(.*)\"$ ]]; then val="${BASH_REMATCH[1]}"; fi
      if [[ "$val" =~ ^\'(.*)\'$ ]]; then val="${BASH_REMATCH[1]}"; fi
      export "$key=$val"
    fi
  done < "$f"
}

load_env_file "$ROOT/.env"
load_env_file "$ROOT/examples/langgraph-openai-agent/.env"

# SQLite — no Postgres.
# Absolute path form is sqlite:////abs/path (FOUR slashes). Build carefully:
# ROOT is /Users/... so strip the leading slash before joining or we get five.
if [[ -z "${DATABASE_URL:-}" || "${DATABASE_URL}" == sqlite* ]]; then
  export DATABASE_URL="sqlite+aiosqlite:////${ROOT#/}/data/harness.db"
fi
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

if [[ ! -d "$ROOT/examples/domain-agents/.venv" ]]; then
  echo "==> Creating domain-agents venv"
  python3 -m venv "$ROOT/examples/domain-agents/.venv"
  # shellcheck disable=SC1091
  source "$ROOT/examples/domain-agents/.venv/bin/activate"
  pip install -q -r "$ROOT/examples/domain-agents/requirements.txt"
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
stop_port 8091
stop_port 5173

# Detach from the parent shell (nohup + disown) so IDE agent cleanup does not
# tear down the stack when the starter command exits.
_run_service() {
  local name="$1" logfile="$2" pidfile="$3" workdir="$4"
  shift 4
  nohup bash -c "
    cd \"$workdir\" || exit 1
    if [[ -f .venv/bin/activate ]]; then source .venv/bin/activate; fi
    exec $(printf '%q ' "$@")
  " >"$logfile" 2>&1 &
  local pid=$!
  echo "$pid" >"$pidfile"
  disown "$pid" 2>/dev/null || true
  echo "    $name pid $pid"
}

echo "==> Starting LangGraph OpenAI agent :8090"
_run_service agent "$ROOT/data/logs/agent.log" "$ROOT/data/pids/agent.pid" \
  "$ROOT/examples/langgraph-openai-agent" \
  uvicorn main:app --host 127.0.0.1 --port 8090

echo "==> Starting domain-agents (AD/AMS/QE) :8091"
OPENAI_API_KEY="${OPENAI_API_KEY:-}" OPENAI_MODEL="${OPENAI_MODEL:-}" \
AZURE_OPENAI_API_KEY="${AZURE_OPENAI_API_KEY:-}" \
AZURE_OPENAI_ENDPOINT="${AZURE_OPENAI_ENDPOINT:-}" \
AZURE_OPENAI_API_VERSION="${AZURE_OPENAI_API_VERSION:-}" \
AZURE_OPENAI_DEPLOYMENT="${AZURE_OPENAI_DEPLOYMENT:-}" \
_run_service domain-agents "$ROOT/data/logs/domain-agents.log" "$ROOT/data/pids/domain-agents.pid" \
  "$ROOT/examples/domain-agents" \
  uvicorn main:app --host 127.0.0.1 --port 8091

echo "==> Starting control-plane :8000"
DATABASE_URL="$DATABASE_URL" AUTH_DEMO="$AUTH_DEMO" AUTO_CREATE_TABLES="$AUTO_CREATE_TABLES" \
CORS_ORIGINS="$CORS_ORIGINS" LANGGRAPH_AGENT_URL="$LANGGRAPH_AGENT_URL" \
HARNESS_PROJECT_ALLOWLIST="${HARNESS_PROJECT_ALLOWLIST:-}" \
HTTP_TIMEOUT_SECONDS="$HTTP_TIMEOUT_SECONDS" \
OPENAI_API_KEY="${OPENAI_API_KEY:-}" OPENAI_MODEL="${OPENAI_MODEL:-}" \
AZURE_OPENAI_API_KEY="${AZURE_OPENAI_API_KEY:-}" \
AZURE_OPENAI_ENDPOINT="${AZURE_OPENAI_ENDPOINT:-}" \
AZURE_OPENAI_API_VERSION="${AZURE_OPENAI_API_VERSION:-}" \
AZURE_OPENAI_DEPLOYMENT="${AZURE_OPENAI_DEPLOYMENT:-}" \
PYTHONPATH="$ROOT/services/control-plane" \
_run_service api "$ROOT/data/logs/api.log" "$ROOT/data/pids/api.pid" \
  "$ROOT/services/control-plane" \
  uvicorn app.main:app --host 127.0.0.1 --port 8000

echo "==> Starting Mission Control UI :5173"
_run_service ui "$ROOT/data/logs/ui.log" "$ROOT/data/pids/ui.pid" \
  "$ROOT/apps/mission-control" \
  npm run dev -- --host 127.0.0.1 --port 5173

echo "==> Waiting for health…"
ok=0
for i in $(seq 1 40); do
  if curl -sf http://127.0.0.1:8090/health >/dev/null 2>&1 \
    && curl -sf http://127.0.0.1:8091/health >/dev/null 2>&1 \
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
  tail -n 20 "$ROOT/data/logs/domain-agents.log" 2>/dev/null || true
fi

echo ""
echo "AI Harness (no Docker) is up"
echo "  UI:            http://127.0.0.1:5173"
echo "  API:           http://127.0.0.1:8000/docs"
echo "  Agent:         http://127.0.0.1:8090/health"
echo "  Domain agents: http://127.0.0.1:8091/agents   (AD / AMS / QE)"
echo "  Login:         admin@harness.local / harness-admin"
echo ""
echo "Register domain agents: make register-domain-agents"
echo "Logs:  $ROOT/data/logs/"
echo "Stop:  $ROOT/scripts/stop-local.sh"
echo ""
echo "Tail logs with: tail -f data/logs/*.log"
