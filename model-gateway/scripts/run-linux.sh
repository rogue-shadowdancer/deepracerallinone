#!/usr/bin/env sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
BIND_HOST="0.0.0.0"
PORT="8080"
DATA_DIR=""
ENV_FILE="${PROJECT_DIR}/.gateway.env"
DRY_RUN="false"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host)
      BIND_HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --data-dir)
      DATA_DIR="$2"
      shift 2
      ;;
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    -h|--help)
      echo "Usage: scripts/run-linux.sh [--host HOST] [--port PORT] [--data-dir DIR] [--env-file FILE] [--dry-run]"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

load_env_file() {
  [ -f "$ENV_FILE" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ""|\#*) continue ;;
      *=*)
        key=${line%%=*}
        value=${line#*=}
        export "$key=$value"
        ;;
    esac
  done < "$ENV_FILE"
}

load_env_file

export PYTHONPATH="${PROJECT_DIR}/src"
if [ -n "$DATA_DIR" ]; then
  export GATEWAY_DATA_DIR="$DATA_DIR"
else
  export GATEWAY_DATA_DIR="${GATEWAY_DATA_DIR:-${PROJECT_DIR}/data}"
fi

PYTHON="${PROJECT_DIR}/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi

if [ "$DRY_RUN" = "true" ]; then
  echo "DeepRacer Model Gateway run dry-run"
  echo "Project: ${PROJECT_DIR}"
  echo "Env file: ${ENV_FILE}"
  echo "Python: ${PYTHON}"
  echo "Data dir: ${GATEWAY_DATA_DIR}"
  echo "User URL: http://${BIND_HOST}:${PORT}/login"
  echo "Admin URL: http://${BIND_HOST}:${PORT}/admin/login"
  exit 0
fi

exec "$PYTHON" -m uvicorn model_gateway.app:app --host "$BIND_HOST" --port "$PORT"
