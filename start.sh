#!/bin/bash
set -e

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Config ────────────────────────────────────────────────────────────────────
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-9999}"
WORKERS="${WORKERS:-1}"
VENV_DIR=".venv"

# ── Working directory = script location ───────────────────────────────────────
cd "$(dirname "$0")"
info "Working directory: $(pwd)"

# ── Virtual environment ───────────────────────────────────────────────────────
if [ -d "$VENV_DIR" ]; then
    # venv already exists — use it directly, no system Python check needed
    info "Found existing venv, activating..."
    source "$VENV_DIR/bin/activate"
else
    # Need to create venv — find a suitable system Python 3.11+
    PYTHON=""
    for cmd in python3.13 python3.12 python3.11 python3; do
        if command -v "$cmd" &>/dev/null; then
            if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
                PYTHON="$cmd"
                break
            fi
        fi
    done
    [ -z "$PYTHON" ] && error "Python 3.11+ not found. Install with: sudo apt install python3.11"
    info "Using Python: $PYTHON ($($PYTHON --version))"

    # Install system packages if needed
    if command -v apt-get &>/dev/null; then
        PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        MISSING=""
        for pkg in "python${PY_VER}-venv" "python${PY_VER}-dev" build-essential; do
            dpkg -s "$pkg" &>/dev/null || MISSING="$MISSING $pkg"
        done
        if [ -n "$MISSING" ]; then
            warn "Installing missing system packages:$MISSING"
            sudo apt-get install -y $MISSING
        fi
    fi

    info "Creating virtual environment..."
    $PYTHON -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
fi

VENV_PYTHON="$VENV_DIR/bin/python3"
VENV_PIP="$VENV_DIR/bin/pip"
[ ! -f "$VENV_PYTHON" ] && VENV_PYTHON="$VENV_DIR/bin/python"
[ ! -f "$VENV_PIP" ]    && VENV_PIP="$VENV_DIR/bin/pip3"
info "Virtualenv: $VENV_PYTHON ($($VENV_PYTHON --version))"

# ── Install dependencies (only when pyproject.toml changes) ──────────────────
MARKER="$VENV_DIR/.deps_installed"
CURRENT_HASH=$(md5sum pyproject.toml 2>/dev/null | cut -d' ' -f1 || echo "")
SAVED_HASH=$(cat "$MARKER" 2>/dev/null || echo "")
if [ "$CURRENT_HASH" != "$SAVED_HASH" ]; then
    info "Installing dependencies..."
    $VENV_PIP install --upgrade pip -q
    $VENV_PIP install \
        "anthropic>=0.40.0" \
        "yfinance>=0.2.40" \
        "sqlalchemy>=2.0" \
        "chromadb>=0.5.0" \
        "sentence-transformers>=3.0" \
        "click>=8.1" \
        "python-dotenv>=1.0" \
        "pydantic-settings>=2.0" \
        "requests>=2.31" \
        "apscheduler>=3.10" \
        "pandas>=2.0" \
        "openai>=1.0.0" \
        "fastapi>=0.111.0" \
        "uvicorn[standard]>=0.30.0" \
        "sse-starlette>=1.8.0" \
        -q
    echo "$CURRENT_HASH" > "$MARKER"
    info "Dependencies installed."
else
    info "Dependencies up to date, skipping install."
fi

# ── .env check ───────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    warn ".env not found — creating from .env.example"
    if [ -f ".env.example" ]; then
        cp .env.example .env
        warn "Edit .env and set your API keys, then re-run this script."
        exit 1
    else
        error ".env and .env.example both missing. Create a .env file first."
    fi
fi

# ── Check required keys ───────────────────────────────────────────────────────
check_env() {
    val=$(grep -E "^$1=" .env 2>/dev/null | cut -d= -f2- | tr -d '[:space:]' || echo "")
    if [ -z "$val" ]; then
        warn ".env: $1 is not set"
    fi
}

BACKEND=$(grep -E "^LLM_BACKEND=" .env 2>/dev/null | cut -d= -f2- | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]' || echo "")
case "$BACKEND" in
    aliyun)   check_env ALIYUN_API_KEY ;;
    anthropic) check_env ANTHROPIC_API_KEY ;;
    zoom)     check_env ZOOM_TOKEN; check_env ZOOM_AGENT_ID ;;
    *) warn "LLM_BACKEND not set or unknown, defaulting to zoom" ;;
esac

# ── Data directory ────────────────────────────────────────────────────────────
mkdir -p data

# ── Start ─────────────────────────────────────────────────────────────────────
info "Starting Stock Analysis API on http://${HOST}:${PORT}"
info "Press Ctrl+C to stop."
echo ""

exec "$VENV_DIR/bin/uvicorn" api.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS"
