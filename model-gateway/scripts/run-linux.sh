#!/usr/bin/env sh
set -eu
PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
export PYTHONPATH="${PROJECT_DIR}/src"
export GATEWAY_DATA_DIR="${GATEWAY_DATA_DIR:-${PROJECT_DIR}/data}"
python -m uvicorn model_gateway.app:app --host 0.0.0.0 --port 8080
