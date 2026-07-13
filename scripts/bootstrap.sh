#!/usr/bin/env sh
set -eu

if [ "$(uname -s)" != "Darwin" ]; then
  echo "Business Intelligence Agent supports macOS only" >&2
  exit 1
fi

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

if ! command -v uv >/dev/null 2>&1; then
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required to install uv" >&2
    exit 1
  fi
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  export PATH
fi

cd "$PROJECT_DIR"
uv sync --frozen
uv run bia detect
