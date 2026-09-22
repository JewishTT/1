#!/usr/bin/env bash
# Create and populate a local Python virtual environment for this repo.
# Usage:
#   bash scripts/setup_venv.sh
#   source .venv/bin/activate
#   pytest -q  # optional

set -euo pipefail

# Move to repo root (script lives in scripts/)
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PY=${PYTHON:-python3}
RECREATE=${RECREATE_VENV:-0}

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "python3 not found. Please install Python 3 and python3-venv (e.g., sudo apt install -y python3 python3-venv)." >&2
  exit 1
fi

# Ensure venv module is available (Debian/Ubuntu often needs python3-venv package)
if ! "$PY" -m venv --help >/dev/null 2>&1; then
  echo "The venv module isn't available. Try: sudo apt update && sudo apt install -y python3-venv" >&2
  exit 1
fi

# Create or recreate venv
if [ "$RECREATE" = "1" ] && [ -d .venv ]; then
  echo "Removing existing virtual environment at .venv ..."
  rm -rf .venv || true
fi

if [ ! -d .venv ] || [ ! -f .venv/bin/activate ]; then
  echo "Creating virtual environment at .venv ..."
  "$PY" -m venv .venv
else
  echo "Using existing virtual environment at .venv"
fi

# Activate
# shellcheck disable=SC1091
source .venv/bin/activate

# Upgrade pip tooling
python -m pip install --upgrade pip setuptools wheel

# Install project requirements
REQ_FILE="orchestrator/requirements.txt"

# Optionally pre-install CPU-only PyTorch to avoid massive CUDA downloads when no GPU is present.
# Set PREFER_TORCH_GPU=1 to skip this and let pip pick GPU builds if appropriate.
if [ -f "$REQ_FILE" ] && grep -qE '(^|[[:space:]])(sentence-transformers|torch)([[:space:]]|$)' "$REQ_FILE"; then
  if [ "${PREFER_TORCH_GPU:-0}" != "1" ] && ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "No NVIDIA GPU detected and PREFER_TORCH_GPU!=1. Installing CPU-only PyTorch wheels to keep the env lightweight..."
    # Best-effort: if this fails, proceed with generic install.
    python -m pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision torchaudio || true
  fi
fi

if [ -f "$REQ_FILE" ]; then
  echo "Installing dependencies from $REQ_FILE ..."
  python -m pip install -r "$REQ_FILE"
else
  echo "Requirements file $REQ_FILE not found. Skipping."
fi

echo
echo "Done. Activate the environment with:"
printf "  source .venv/bin/activate\n"

echo "To run tests:"
printf "  pytest -q\n"
