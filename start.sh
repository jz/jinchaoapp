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

# ── Pre-flight checks ──────────────────────────────────────────────────────
if [ ! -f "$KATAGO_PATH" ]; then
  echo "ERROR: KataGo binary not found: $KATAGO_PATH" >&2
  echo "       Run './install_katago.sh' to install it." >&2
  exit 1
fi

if [ ! -f "$KATAGO_MODEL" ]; then
  echo "ERROR: KataGo model not found: $KATAGO_MODEL" >&2
  echo "       Run './install_katago.sh' to download it." >&2
  exit 1
fi
# ──────────────────────────────────────────────────────────────────────────

echo "Starting web Go server on port ${PORT}..."
echo "  KataGo:  $KATAGO_PATH"
echo "  Model:   $KATAGO_MODEL"
echo "  Config:  $KATAGO_CONFIG"
echo ""

# Prefer venv python if available
PYTHON=python3
if [ -f ./venv/bin/python3 ]; then
  PYTHON=./venv/bin/python3
fi

exec "$PYTHON" app.py
