#!/usr/bin/env sh
# setup.sh — Download KataGo Eigen binary + small model, then install Python deps.
# Supports both Linux and FreeBSD.

set -eu

# ── Config ─────────────────────────────────────────────────────────────────
KATAGO_VERSION="1.15.3"

# b6c96 network — very small (~3.5 MB), ~150 MB RAM. Good for 1 GB VPS.
MODEL_FILE="kata1-b6c96-s175395328-d26217734.bin.gz"
MODEL_URL="https://media.katagotraining.org/uploaded/networks/models/kata1/${MODEL_FILE}"

BIN_DIR="./katago_bin"
MODEL_DIR="./models"
# ───────────────────────────────────────────────────────────────────────────

OS=$(uname -s)
ARCH=$(uname -m)
echo "==> Detected OS: $OS ($ARCH)"

echo "==> Creating directories..."
mkdir -p "$BIN_DIR" "$MODEL_DIR" config

# ── System dependencies ───────────────────────────────────────────────────
install_deps() {
  case "$OS" in
    FreeBSD)
      echo "==> Installing system packages (pkg)..."
      pkg install -y python3 py311-pip curl unzip eigen cmake git gmake
      ;;
    Linux)
      if command -v apt-get >/dev/null 2>&1; then
        echo "==> Installing system packages (apt)..."
        apt-get update && apt-get install -y python3 python3-pip unzip curl git
      elif command -v yum >/dev/null 2>&1; then
        echo "==> Installing system packages (yum)..."
        yum install -y python3 python3-pip unzip curl git
      fi
      ;;
  esac
}

# ── KataGo binary ─────────────────────────────────────────────────────────
install_katago() {
  if [ -f "$BIN_DIR/katago" ]; then
    echo "==> KataGo binary already exists, skipping."
    return
  fi

  case "$OS" in
    Linux)
      KATAGO_ZIP="katago-v${KATAGO_VERSION}-eigen-linux-x64.zip"
      KATAGO_URL="https://github.com/lightvector/KataGo/releases/download/v${KATAGO_VERSION}/${KATAGO_ZIP}"
      echo "==> Downloading KataGo v${KATAGO_VERSION} (Eigen/CPU, Linux)..."
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
      ;;
    FreeBSD)
      echo "==> Building KataGo v${KATAGO_VERSION} from source (Eigen/CPU, FreeBSD)..."
      BUILD_DIR="/tmp/katago_build"
      rm -rf "$BUILD_DIR"
      mkdir -p "$BUILD_DIR"

      echo "    Downloading source..."
      curl -L --retry 4 --retry-delay 2 \
        -o "$BUILD_DIR/katago.tar.gz" \
        "https://github.com/lightvector/KataGo/archive/refs/tags/v${KATAGO_VERSION}.tar.gz"

      echo "    Extracting..."
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

      echo "    Running cmake..."
      cmake . -DUSE_BACKEND=EIGEN -DCMAKE_CXX_FLAGS="-O3" 2>&1 | tail -5

      echo "    Building (this may take a few minutes)..."
      NPROC=$(sysctl -n hw.ncpu 2>/dev/null || echo 1)
      gmake -j"$NPROC" 2>&1 | tail -5

      cd - >/dev/null
      cp "$SRC_DIR/katago" "$BIN_DIR/katago"
      chmod +x "$BIN_DIR/katago"
      rm -rf "$BUILD_DIR"
      ;;
    *)
      echo "ERROR: Unsupported OS: $OS" >&2
      exit 1
      ;;
  esac

  echo "==> KataGo installed at $BIN_DIR/katago"
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

# ── Python deps ────────────────────────────────────────────────────────────
install_python() {
  echo "==> Installing Python dependencies..."
  # FreeBSD uses python3.11 -m pip; Linux may have pip3 directly
  if command -v pip3 >/dev/null 2>&1; then
    pip3 install -r requirements.txt --quiet --break-system-packages 2>/dev/null \
      || pip3 install -r requirements.txt --quiet
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m pip install -r requirements.txt --quiet --break-system-packages 2>/dev/null \
      || python3 -m pip install -r requirements.txt --quiet
  else
    echo "ERROR: python3 or pip3 not found" >&2
    exit 1
  fi
}

# ── .env ──────────────────────────────────────────────────────────────────
setup_env() {
  if [ ! -f .env ]; then
    cp .env.example .env
    echo "==> Created .env from .env.example"
  fi
}

# ── Run ────────────────────────────────────────────────────────────────────
install_deps
install_katago
install_model
install_python
setup_env

echo ""
echo "Setup complete!"
echo "  Start the server with:  sh start.sh"
echo "  Then open:              http://<your-vps-ip>:5000"
