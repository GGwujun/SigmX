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

start_worker="${VIBE_TRADING_START_MARKET_SYNC_WORKER:-1}"
case "$start_worker" in
  0|false|False|FALSE|no|No|NO)
    ;;
  *)
    vibe-trading-sync worker --interval "${MARKET_SYNC_WORKER_INTERVAL:-60}" &
    worker_pid=$!
    ;;
esac

vibe-trading serve --host "${VIBE_TRADING_HOST:-0.0.0.0}" --port "${VIBE_TRADING_PORT:-8899}" &
server_pid=$!

status=0
wait "$server_pid" || status=$?
shutdown
exit "$status"
