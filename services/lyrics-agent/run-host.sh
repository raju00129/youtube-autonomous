#!/usr/bin/env bash
# Run lyrics-agent on the Mac host so Cursor CLI (cursor-agent) can be used.
# Then point Docker backend at it:
#   LYRICS_AGENT_URL=http://host.docker.internal:8020
#   docker compose up -d --force-recreate backend
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

export PORT="${PORT:-8020}"
export CURSOR_LLM_MODEL="${CURSOR_LLM_MODEL:-composer-2.5}"
export LYRICS_BACKEND="${LYRICS_BACKEND:-auto}"
export LYRICS_WORKSPACE="${LYRICS_WORKSPACE:-/tmp/ragam-lyrics-workspace}"
export CURSOR_CLI_PATH="${CURSOR_CLI_PATH:-$HOME/.local/bin/cursor-agent}"

if [[ -f ../../.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source ../../.env
  set +a
fi

export CURSOR_LLM_MODEL="${CURSOR_LLM_MODEL:-composer-2.5}"
export LYRICS_BACKEND="${LYRICS_BACKEND:-auto}"

if [[ ! -d node_modules ]]; then
  npm install
fi

echo "Starting lyrics-agent on host :$PORT model=$CURSOR_LLM_MODEL backend=$LYRICS_BACKEND cli=${CURSOR_CLI_PATH}"
exec node src/server.mjs
