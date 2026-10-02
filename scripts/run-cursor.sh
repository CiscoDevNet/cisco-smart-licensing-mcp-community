#!/usr/bin/env bash
# Cursor / Claude Desktop wrapper for cisco-smart-licensing-mcp.
#
# Sources the project-local `.env` (so credentials never get expanded into
# command-line arguments and never live in mcp.json) and exec's the installed
# `cisco-smart-licensing-mcp` binary on stdio.
#
# Usage (in ~/.cursor/mcp.json):
#
#   "cisco-smart-licensing": {
#     "command": "/path/to/cisco-smart-licensing-mcp-community/scripts/run-cursor.sh"
#   }
#
# The wrapper is intentionally minimal: with zero creds in .env the server
# still boots (registering zero tools), which is useful for smoke-testing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"
BIN="${PROJECT_ROOT}/.venv/bin/cisco-smart-licensing-mcp"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

if [[ ! -x "${BIN}" ]]; then
  echo "cisco-smart-licensing-mcp binary not found at ${BIN}" >&2
  echo "Install with: cd ${PROJECT_ROOT} && python -m venv .venv && source .venv/bin/activate && pip install -e ." >&2
  exit 127
fi

exec "${BIN}"
