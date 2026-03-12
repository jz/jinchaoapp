#!/usr/bin/env sh
# start.sh — Start the web Go server.

set -eu

# Load .env if present
if [ -f .env ]; then
  set -a
  . .env
  set +a
fi

export KATAGO_PATH="${KATAGO_PATH:-./katago_bin/katago}"
export KATAGO_MODEL="${KATAGO_MODEL:-./models/model.bin.gz}"
export KATAGO_CONFIG="${KATAGO_CONFIG:-./config/gtp.cfg}"
export PORT="${PORT:-5000}"

echo "Starting web Go server on port ${PORT}..."
echo "  KataGo:  $KATAGO_PATH"
echo "  Model:   $KATAGO_MODEL"
echo "  Config:  $KATAGO_CONFIG"
echo ""

exec python3 app.py
