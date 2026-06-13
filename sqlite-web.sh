#!/usr/bin/env bash
set -euo pipefail

IMAGE="${SQLITE_WEB_IMAGE:-ghcr.io/coleifer/sqlite-web:latest}"
START_PORT=5666

usage() {
  cat <<'EOF'
Simple script to run sqlite-web in a Docker container.

Usage:
  sqlite-web.sh [--port PORT] <database-file>
  sqlite-web.sh [-p PORT] <database-file>
  sqlite-web.sh [-h|--help]

Options:
  -p, --port PORT   Host port to bind to. If omitted, the next free port
                    starting from 5666 is selected.
  -h, --help        Show this help.

Examples:
  sqlite-web.sh ./app.db
  sqlite-web.sh -p 4242 ./runtime/app.db

Environment:
  SQLITE_WEB_IMAGE  Override Docker image
                    (default: ghcr.io/coleifer/sqlite-web:latest)
EOF
}

err() {
  echo "Error: $*" >&2
  exit 1
}

is_port_free() {
  local port="$1"

  if command -v ss >/dev/null 2>&1; then
    ! ss -H -ltn "( sport = :$port )" | grep -q .
    return
  fi

  if command -v lsof >/dev/null 2>&1; then
    ! lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return
  fi

  if command -v netstat >/dev/null 2>&1; then
    ! netstat -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "(^|[.:])${port}$"
    return
  fi

  err "Could not detect a port-checking tool. Install ss, lsof, or netstat."
}

pick_port() {
  local port="$START_PORT"

  while true; do
    if is_port_free "$port"; then
      echo "$port"
      return 0
    fi
    port=$((port + 1))
  done
}

PORT=""
DB_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    -p|--port)
      [[ $# -ge 2 ]] || err "Missing value for $1"
      PORT="$2"
      shift 2
      ;;
    --port=*)
      PORT="${1#*=}"
      shift
      ;;
    --)
      shift
      break
      ;;
    -*)
      err "Unknown option: $1"
      ;;
    *)
      if [[ -n "$DB_PATH" ]]; then
        err "Only one database file may be specified"
      fi
      DB_PATH="$1"
      shift
      ;;
  esac
done

[[ -n "$DB_PATH" ]] || { usage; exit 1; }

if [[ ! -f "$DB_PATH" ]]; then
  err "Database file not found: $DB_PATH"
fi

if [[ -n "$PORT" ]]; then
  [[ "$PORT" =~ ^[0-9]+$ ]] || err "Port must be a number"
  (( PORT >= 1 && PORT <= 65535 )) || err "Port must be between 1 and 65535"
  is_port_free "$PORT" || err "Port $PORT is already in use"
else
  PORT="$(pick_port)"
fi

DB_ABS="$(realpath "$DB_PATH")"
DB_DIR="$(dirname "$DB_ABS")"
DB_FILE="$(basename "$DB_ABS")"

command -v docker >/dev/null 2>&1 || err "docker is not installed or not in PATH"

echo "Starting webinterface on http://0.0.0.0:${PORT}"

exec docker run -it --rm \
  -p "${PORT}:8080" \
  -v "${DB_DIR}:/data" \
  "${IMAGE}" \
  "/data/${DB_FILE}"
