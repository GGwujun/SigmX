#!/bin/sh
set -eu

shutdown() {
  if [ -n "${worker_pid:-}" ]; then
    kill "$worker_pid" 2>/dev/null || true
  fi
  if [ -n "${server_pid:-}" ]; then
    kill "$server_pid" 2>/dev/null || true
  fi
}

trap shutdown INT TERM

# Source layout: project code lives under /app/agent (api_server.py, src/...).
# The full image installs it via `pip install -e .` (so console scripts like
# `vibe-trading` exist and `src` is importable everywhere); the slim Data Hub
# image does NOT install the project, so it needs PYTHONPATH=/app/agent. Setting
# PYTHONPATH unconditionally is harmless in both and lets us invoke via
# `python -m` in either image without depending on console-script entry points.
export PYTHONPATH="${PYTHONPATH:-/app/agent}"

start_worker="${VIBE_TRADING_START_MARKET_SYNC_WORKER:-0}"
case "$start_worker" in
  0|false|False|FALSE|no|No|NO)
    ;;
  *)
    python -m src.data.market_sync_worker worker --interval "${MARKET_SYNC_WORKER_INTERVAL:-60}" &
    worker_pid=$!
    ;;
esac

python -m api_server --host "${VIBE_TRADING_HOST:-0.0.0.0}" --port "${VIBE_TRADING_PORT:-8899}" &
server_pid=$!

status=0
wait "$server_pid" || status=$?
shutdown
exit "$status"
