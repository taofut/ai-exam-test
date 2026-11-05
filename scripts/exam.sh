#!/usr/bin/env bash
set -euo pipefail

material_script_path="${BASH_SOURCE[0]}"
if [[ "$material_script_path" == */* ]]; then
  MATERIAL_ROOT="$(cd -- "${material_script_path%/*}/.." && pwd)"
else
  MATERIAL_ROOT="$(cd .. && pwd)"
fi
MATERIAL_BACKEND="$MATERIAL_ROOT/app/backend"
MATERIAL_FRONTEND="$MATERIAL_ROOT/app/frontend"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$MATERIAL_ROOT/runtime/cache/uv}"
export npm_config_cache="${npm_config_cache:-$MATERIAL_ROOT/runtime/cache/npm}"

material_command="${1:-}"
if [[ $# -gt 0 ]]; then shift; fi
if [[ $# -gt 0 ]]; then
  printf 'Unexpected arguments. Usage: bash exam {preflight|start|reset|test|starter|verify-data}\n' >&2
  exit 2
fi
if [[ "$material_command" == test || "$material_command" == starter ]]; then
  mkdir -p "$MATERIAL_ROOT/runtime/cache/pytest-tmp"
fi
if [[ "$material_command" == start || "$material_command" == reset ]]; then
  if [[ -z "${DATABASE_URL:-}" ]]; then
    mkdir -p "$MATERIAL_ROOT/runtime/data"
    material_shared_database="$MATERIAL_ROOT/runtime/data/materialops.db"
    if command -v cygpath >/dev/null 2>&1; then
      material_shared_database="$(cygpath -m "$material_shared_database")"
    fi
    export DATABASE_URL="sqlite:///$material_shared_database"
  fi
  printf 'Using the shared application database (start preserves initialized data).\n'
fi

prepare_backend() {
  (cd "$MATERIAL_BACKEND" && uv sync --frozen --quiet)
}

prepare_frontend() {
  if [[ ! -d "$MATERIAL_FRONTEND/node_modules" ]]; then
    (cd "$MATERIAL_FRONTEND" && npm ci --no-audit --no-fund)
  fi
}

case "$material_command" in
  preflight)
    failed=0
    for executable in uv node npm; do
      if command -v "$executable" >/dev/null 2>&1; then
        printf '[ok] %s\n' "$executable"
      else
        printf '[missing] %s\n' "$executable"
        failed=1
      fi
    done
    exit "$failed"
    ;;
  start)
    prepare_backend
    prepare_frontend
    (cd "$MATERIAL_BACKEND" && uv run python -m materialops.cli seed)
    material_api_port="${MATERIAL_API_PORT:-8000}"
    material_web_port="${MATERIAL_WEB_PORT:-5173}"
    (cd "$MATERIAL_BACKEND" && uv run uvicorn materialops.main:app --host 127.0.0.1 --port "$material_api_port") &
    material_api_pid=$!
    (cd "$MATERIAL_FRONTEND" && VITE_API_TARGET="http://127.0.0.1:$material_api_port" npm run dev -- --host 127.0.0.1 --port "$material_web_port" --strictPort) &
    material_web_pid=$!
    trap 'kill "$material_api_pid" "$material_web_pid" 2>/dev/null || true' EXIT INT TERM
    printf 'MaterialOps: http://127.0.0.1:%s\nAPI: http://127.0.0.1:%s/docs\n' "$material_web_port" "$material_api_port"
    # Portable replacement for `wait -n`, which macOS ships no support for (bash 3.2).
    while kill -0 "$material_api_pid" 2>/dev/null && kill -0 "$material_web_pid" 2>/dev/null; do
      sleep 2
    done
    printf 'A service exited; stopping the other service.\n' >&2
    exit 1
    ;;
  reset)
    prepare_backend
    (cd "$MATERIAL_BACKEND" && uv run python -m materialops.cli reset)
    printf 'MaterialOps exam data reset.\n'
    ;;
  test)
    prepare_backend
    prepare_frontend
    (cd "$MATERIAL_BACKEND" && uv run pytest --basetemp "$MATERIAL_ROOT/runtime/cache/pytest-tmp/backend")
    (cd "$MATERIAL_BACKEND" && uv run pytest ../../scripts/tests --basetemp "$MATERIAL_ROOT/runtime/cache/pytest-tmp/resources" -o "cache_dir=$MATERIAL_ROOT/runtime/cache/pytest")
    (cd "$MATERIAL_FRONTEND" && npm test)
    (cd "$MATERIAL_FRONTEND" && npm run build)
    ;;
  starter)
    prepare_backend
    (cd "$MATERIAL_BACKEND" && uv run pytest -m starter --basetemp "$MATERIAL_ROOT/runtime/cache/pytest-tmp/starter" -q)
    ;;
  verify-data)
    prepare_backend
    (cd "$MATERIAL_BACKEND" && uv run python ../../scripts/verify_resources.py)
    ;;
  *)
    printf 'Usage: bash exam {preflight|start|reset|test|starter|verify-data}\n' >&2
    exit 2
    ;;
esac
