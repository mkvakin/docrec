#!/usr/bin/env bash
set -euo pipefail

# Run from repo root
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

# Enter server dir
cd server

# Create/activate venv
python3 -m venv .venv || true
# shellcheck disable=SC1091
source .venv/bin/activate

# Install deps
pip install --upgrade pip
pip install -r requirements.txt

# Defaults for local testing (override in environment)
export UPLOAD_DIR="${UPLOAD_DIR:-/tmp/docrec_uploads}"
export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-local-docrec}"
export FIRESTORE_EMULATOR_HOST="${FIRESTORE_EMULATOR_HOST:-localhost:8080}"
mkdir -p "$UPLOAD_DIR"

# Run server
export PORT="${PORT:-8081}"
echo "Starting server on :$PORT (uploads -> $UPLOAD_DIR)"
python app.py