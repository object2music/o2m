#!/bin/bash
# watch_restart.sh — host-side daemon that restarts mopidy+o2m when o2m API requests it.
# Run from the o2m-docker project root, e.g.:
#   nohup ./scripts/watch_restart.sh &
# Or install as a systemd service (see below).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SIGNAL_FILE="$PROJECT_DIR/o2m/tmp/restart_requested"

echo "[watch_restart] started — watching $SIGNAL_FILE"

while true; do
    if [ -f "$SIGNAL_FILE" ]; then
        rm -f "$SIGNAL_FILE"
        echo "[watch_restart] restart requested — restarting mopidy and o2m…"
        cd "$PROJECT_DIR"
        docker compose --profile prod restart mopidy o2m
        echo "[watch_restart] done"
    fi
    sleep 2
done
