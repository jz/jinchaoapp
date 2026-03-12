#!/usr/bin/env bash
# setup_linux.sh — Install KataGo Eigen binary + model + Python deps on Linux.

set -eu

# ── Config ─────────────────────────────────────────────────────────────────
KATAGO_VERSION="1.15.3"

# b6c96 network — very small (~3.5 MB), ~150 MB RAM. Good for 1 GB VPS.
MODEL_FILE="kata1-b6c96-s175395328-d26217734.bin.gz"
MODEL_URL="https://media.katagotraining.org/uploaded/networks/models/kata1/${MODEL_FILE}"

BIN_DIR="./katago_bin"
MODEL_DIR="./models"
ARCH=$(uname -m)
# ───────────────────────────────────────────────────────────────────────────

echo "==> Linux setup (arch: $ARCH)"
mkdir -p "$BIN_DIR" "$MODEL_DIR" config

# ── System dependencies ────────────────────────────────────────────────────
install_sys_deps() {
  local pkgs="python3 unzip curl git"
  if command -v apt-get >/dev/null 2>&1; then
    echo "==> Installing system packages (apt)..."
    apt-get update -q && apt-get install -y $pkgs
  elif command -v dnf >/dev/null 2>&1; then
    echo "==> Installing system packages (dnf)..."
    dnf install -y $pkgs python3-pip
  elif command -v yum >/dev/null 2>&1; then
    echo "==> Installing system packages (yum)..."
    yum install -y $pkgs python3-pip
  else
    echo "WARNING: No known package manager found; skipping system deps."
  fi
}

# ── KataGo binary ─────────────────────────────────────────────────────────
install_katago() {
  if [ -f "$BIN_DIR/katago" ]; then
    echo "==> KataGo binary already exists, skipping."
    return
  fi

  case "$ARCH" in
    x86_64)
      KATAGO_ZIP="katago-v${KATAGO_VERSION}-eigen-linux-x64.zip"
      KATAGO_URL="https://github.com/lightvector/KataGo/releases/download/v${KATAGO_VERSION}/${KATAGO_ZIP}"
      echo "==> Downloading KataGo v${KATAGO_VERSION} (Eigen/CPU, x86_64)..."
      curl -L --retry 4 --retry-delay 2 -o "/tmp/${KATAGO_ZIP}" "$KATAGO_URL"
      echo "==> Extracting..."
      unzip -q "/tmp/${KATAGO_ZIP}" -d "/tmp/katago_extract"
      BINARY=$(find /tmp/katago_extract -name "katago" -type f | head -n1)
      if [ -z "$BINARY" ]; then
        echo "ERROR: could not find katago binary in zip" >&2
        exit 1
      fi
      cp "$BINARY" "$BIN_DIR/katago"
      chmod +x "$BIN_DIR/katago"
      rm -rf "/tmp/${KATAGO_ZIP}" /tmp/katago_extract
      echo "==> KataGo installed at $BIN_DIR/katago"
      ;;
    aarch64|arm64)
      echo "==> No prebuilt KataGo binary for $ARCH; building from source..."
      for tool in cmake g++; do
        if ! command -v $tool >/dev/null 2>&1; then
          echo "ERROR: $tool not found. Install with: apt-get install -y cmake g++ libeigen3-dev" >&2
          exit 1
        fi
      done
      if [ ! -d /usr/include/eigen3 ] && [ ! -d /usr/local/include/eigen3 ]; then
        echo "ERROR: Eigen3 headers not found. Install with: apt-get install -y libeigen3-dev" >&2
        exit 1
      fi

      BUILD_DIR="/tmp/katago_build"
      rm -rf "$BUILD_DIR" && mkdir -p "$BUILD_DIR"
      curl -L --retry 4 --retry-delay 2 \
        -o "$BUILD_DIR/katago.tar.gz" \
        "https://github.com/lightvector/KataGo/archive/refs/tags/v${KATAGO_VERSION}.tar.gz"
      tar -xzf "$BUILD_DIR/katago.tar.gz" -C "$BUILD_DIR"
      # KataGo cmake needs a git repo to generate gitinfoupdated.h
      REPO_DIR="$BUILD_DIR/KataGo-${KATAGO_VERSION}"
      git -C "$REPO_DIR" init -q
      git -C "$REPO_DIR" add -A
      git -C "$REPO_DIR" -c user.email="build@localhost" -c user.name="build" \
        commit -q -m "tarball" --allow-empty
      git -C "$REPO_DIR" tag "v${KATAGO_VERSION}"
      SRC_DIR="$REPO_DIR/cpp"
      cd "$SRC_DIR"
      cmake . -DUSE_BACKEND=EIGEN -DCMAKE_CXX_FLAGS="-O2" 2>&1 | tail -5
      NPROC=$(nproc 2>/dev/null || echo 1)
      make -j"$NPROC" 2>&1 | tail -5
      cd - >/dev/null
      cp "$SRC_DIR/katago" "$BIN_DIR/katago"
      chmod +x "$BIN_DIR/katago"
      rm -rf "$BUILD_DIR"
      echo "==> KataGo installed at $BIN_DIR/katago"
      ;;
    *)
      echo "ERROR: Unsupported architecture: $ARCH" >&2
      exit 1
      ;;
  esac
}

# ── Model ──────────────────────────────────────────────────────────────────
install_model() {
  if [ -f "$MODEL_DIR/model.bin.gz" ]; then
    echo "==> Model already exists, skipping."
    return
  fi
  echo "==> Downloading KataGo model (b6c96, ~3.5 MB)..."
  curl -L --retry 4 --retry-delay 2 -o "$MODEL_DIR/model.bin.gz" "$MODEL_URL"
  echo "==> Model saved to $MODEL_DIR/model.bin.gz"
}

# ── Python venv + deps ─────────────────────────────────────────────────────
install_python() {
  echo "==> Setting up Python virtual environment..."
  if [ ! -d venv ]; then
    # Try standard venv first; fall back to --without-pip + bootstrap
    if python3 -m venv venv 2>/dev/null; then
      echo "    venv created."
    else
      python3 -m venv --without-pip venv
      echo "    Bootstrapping pip inside venv..."
      curl -fsSL https://bootstrap.pypa.io/get-pip.py | venv/bin/python3 - --quiet
    fi
  fi

  echo "==> Installing Python dependencies into venv..."
  venv/bin/pip install -r requirements.txt --quiet
}

# ── .env ──────────────────────────────────────────────────────────────────
setup_env() {
  if [ ! -f .env ]; then
    cp .env.example .env
    echo "==> Created .env from .env.example"
  fi
}

# ── Run ────────────────────────────────────────────────────────────────────
install_sys_deps
install_katago
install_model
install_python
setup_env

echo ""
echo "Setup complete!"
echo "  Start the server with:  sh start.sh"
echo "  Then open:              http://<your-vps-ip>:5000"
