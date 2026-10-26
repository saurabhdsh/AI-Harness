#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

for name in api agent ui; do
  pidfile="$ROOT/data/pids/${name}.pid"
  if [[ -f "$pidfile" ]]; then
    pid="$(cat "$pidfile")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping $name (pid $pid)"
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$pidfile"
  fi
done

for port in 8000 8090 5173; do
  if lsof -ti:"$port" >/dev/null 2>&1; then
    echo "Freeing port $port"
    lsof -ti:"$port" | xargs kill -9 2>/dev/null || true
  fi
done

echo "Local Harness stopped."
