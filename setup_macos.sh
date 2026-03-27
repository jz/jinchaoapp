#!/usr/bin/env bash
# setup_macos.sh — Install KataGo + model + Python deps on macOS (Intel & Apple Silicon).

set -eu

# ── Config ─────────────────────────────────────────────────────────────────
KATAGO_VERSION="1.15.3"

# b18c384nbt human-style model (~99 MB download, ~300 MB RAM). Hosted on GitHub.
MODEL_FILE="b18c384nbt-humanv0.bin.gz"
MODEL_URL="https://github.com/lightvector/KataGo/releases/download/v1.15.0/${MODEL_FILE}"

BIN_DIR="./katago_bin"
MODEL_DIR="./models"
ARCH=$(uname -m)
# ───────────────────────────────────────────────────────────────────────────

echo "==> macOS setup (arch: $ARCH)"
mkdir -p "$BIN_DIR" "$MODEL_DIR" config

# ── Homebrew ───────────────────────────────────────────────────────────────
require_brew() {
  if ! command -v brew >/dev/null 2>&1; then
    echo "ERROR: Homebrew not found. Install it from https://brew.sh and re-run." >&2
    exit 1
  fi
}

# ── KataGo binary ──────────────────────────────────────────────────────────
install_katago() {
  if [ -f "$BIN_DIR/katago" ]; then
    echo "==> KataGo binary already exists, skipping."
    return
  fi

  # KataGo does not ship macOS prebuilt binaries; use Homebrew.
  require_brew
  echo "==> Installing KataGo via Homebrew..."
  brew install katago
  BREW_KATAGO=$(brew --prefix katago)/bin/katago
  if [ ! -f "$BREW_KATAGO" ]; then
    BREW_KATAGO=$(command -v katago 2>/dev/null || true)
  fi
  if [ -z "$BREW_KATAGO" ] || [ ! -f "$BREW_KATAGO" ]; then
    echo "ERROR: KataGo binary not found after brew install." >&2
    exit 1
  fi
  cp "$BREW_KATAGO" "$BIN_DIR/katago"
  chmod +x "$BIN_DIR/katago"
  echo "==> KataGo installed at $BIN_DIR/katago"
}

# ── Model ──────────────────────────────────────────────────────────────────
install_model() {
  if [ -f "$MODEL_DIR/model.bin.gz" ]; then
    echo "==> Model already exists, skipping."
    return
  fi
  echo "==> Downloading KataGo model (~99 MB)..."
  curl -L --retry 4 --retry-delay 2 -o "$MODEL_DIR/model.bin.gz" "$MODEL_URL"
  echo "==> Model saved to $MODEL_DIR/model.bin.gz"
}

# ── Python venv + deps ─────────────────────────────────────────────────────
install_python() {
  # Ensure python3 is available (ships with Xcode CLT or brew)
  if ! command -v python3 >/dev/null 2>&1; then
    require_brew
    echo "==> Installing python3 via Homebrew..."
    brew install python3
  fi

  echo "==> Setting up Python virtual environment..."
  if [ ! -d venv ]; then
    python3 -m venv venv
    echo "    venv created."
  fi

  echo "==> Installing Python dependencies..."
  venv/bin/pip install -r requirements.txt --quiet
}

# ── .env ───────────────────────────────────────────────────────────────────
setup_env() {
  if [ ! -f .env ]; then
    cp .env.example .env
    echo "==> Created .env from .env.example"
  fi
}

# ── Run ────────────────────────────────────────────────────────────────────
install_katago
install_model
install_python
setup_env

echo ""
echo "Setup complete!"
echo "  Start the server with:  sh start.sh"
echo "  Then open:              http://localhost:5000"
