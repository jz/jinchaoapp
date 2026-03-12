#!/usr/bin/env bash
# setup.sh — Download KataGo Eigen binary + small model, then install Python deps.
# Run once on your VPS after cloning the repo.

set -euo pipefail

# ── Config ─────────────────────────────────────────────────────────────────
KATAGO_VERSION="1.15.3"
KATAGO_ZIP="katago-v${KATAGO_VERSION}-eigen-linux-x64.zip"
KATAGO_URL="https://github.com/lightvector/KataGo/releases/download/v${KATAGO_VERSION}/${KATAGO_ZIP}"

# b6c96 network — very small (~3.5 MB), ~150 MB RAM. Good for 1 GB VPS.
MODEL_FILE="kata1-b6c96-s175395328-d26217734.bin.gz"
MODEL_URL="https://media.katagotraining.org/uploaded/networks/models/kata1/${MODEL_FILE}"

BIN_DIR="./katago_bin"
MODEL_DIR="./models"
# ───────────────────────────────────────────────────────────────────────────

echo "==> Creating directories..."
mkdir -p "$BIN_DIR" "$MODEL_DIR" config

# ── KataGo binary ──────────────────────────────────────────────────────────
if [ -f "$BIN_DIR/katago" ]; then
  echo "==> KataGo binary already exists, skipping download."
else
  echo "==> Downloading KataGo v${KATAGO_VERSION} (Eigen/CPU)..."
  curl -L --retry 4 --retry-delay 2 -o "/tmp/${KATAGO_ZIP}" "$KATAGO_URL"

  echo "==> Extracting..."
  unzip -q "/tmp/${KATAGO_ZIP}" -d "/tmp/katago_extract"
  # The zip contains a single binary named 'katago'
  BINARY=$(find /tmp/katago_extract -name "katago" -type f | head -n1)
  if [ -z "$BINARY" ]; then
    echo "ERROR: could not find katago binary in zip" >&2
    exit 1
  fi
  cp "$BINARY" "$BIN_DIR/katago"
  chmod +x "$BIN_DIR/katago"
  rm -rf "/tmp/${KATAGO_ZIP}" /tmp/katago_extract
  echo "==> KataGo installed at $BIN_DIR/katago"
fi

# ── Model ──────────────────────────────────────────────────────────────────
if [ -f "$MODEL_DIR/model.bin.gz" ]; then
  echo "==> Model already exists, skipping download."
else
  echo "==> Downloading KataGo model (b6c96, ~3.5 MB)..."
  curl -L --retry 4 --retry-delay 2 -o "$MODEL_DIR/model.bin.gz" "$MODEL_URL"
  echo "==> Model saved to $MODEL_DIR/model.bin.gz"
fi

# ── Python deps ────────────────────────────────────────────────────────────
echo "==> Installing Python dependencies..."
pip3 install -r requirements.txt --quiet

# ── .env ──────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> Created .env from .env.example"
fi

echo ""
echo "✓ Setup complete!"
echo "  Start the server with:  bash start.sh"
echo "  Then open:              http://<your-vps-ip>:5000"
