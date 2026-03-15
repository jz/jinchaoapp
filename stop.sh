#!/usr/bin/env sh
# stop.sh — Stop the web Go server and KataGo.

PIDFILE="${PIDFILE:-/tmp/jinchao.pid}"

if [ -f "$PIDFILE" ]; then
  PID=$(cat "$PIDFILE")
  if kill -0 "$PID" 2>/dev/null; then
    echo "Stopping server (pid $PID)..."
    kill "$PID"
    # Wait up to 5 seconds for clean exit
    i=0
    while kill -0 "$PID" 2>/dev/null && [ $i -lt 10 ]; do
      sleep 0.5
      i=$((i + 1))
    done
    if kill -0 "$PID" 2>/dev/null; then
      echo "Force-killing pid $PID..."
      kill -9 "$PID"
    fi
  else
    echo "PID $PID not running."
  fi
  rm -f "$PIDFILE"
else
  # Fall back to searching by process name
  PIDS=$(pgrep -f 'python.*app\.py' 2>/dev/null || true)
  if [ -n "$PIDS" ]; then
    echo "Stopping server (pids: $PIDS)..."
    kill $PIDS
  else
    echo "Server is not running."
  fi
fi
