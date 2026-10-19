#!/usr/bin/env bash
# Runs subedit from PyPI through uvx, so the plugin needs nothing installed but uv.
# With "prepare", it warms the same environment in the background instead,
# because the first run installs subedit and downloads Vale, which no edit should wait on.
set -uo pipefail

SPEC='subedit[vale]>=0.2.0'
# A bare uvx takes the first Python it finds, which on a stock Mac is too old for subedit.
PYTHON='>=3.11'

if ! command -v uvx >/dev/null 2>&1; then
    cat >&2 <<'MESSAGE'
subedit needs uv, so comment checks are not running.

    curl -LsSf https://astral.sh/uv/install.sh | sh

Install it, or remove the subedit plugin.
MESSAGE
    exit 1
fi

if [ "${1:-}" = prepare ]; then
    nohup uvx --python "$PYTHON" --from "$SPEC" vale --version >/dev/null 2>&1 &
    exit 0
fi

exec uvx --python "$PYTHON" --from "$SPEC" subedit-hook
