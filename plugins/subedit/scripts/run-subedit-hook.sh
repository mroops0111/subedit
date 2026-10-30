#!/usr/bin/env bash
# Runs subedit from PyPI through uvx, so the plugin needs nothing installed but uv.
# With "prepare", it warms the same environment in the background instead,
# because the first run installs subedit and downloads Vale, which no edit should wait on.
set -uo pipefail

SPEC='subedit[vale]>=0.3.2'
# A bare uvx takes the first Python it finds, which on a stock Mac is too old for subedit.
PYTHON='>=3.11'

# The plugin reaches every session, so it acts only in a project that configures subedit,
# with a subedit.toml or a [tool.subedit] table in pyproject.toml, here or in a parent directory.
adopts_subedit() {
    local directory="$1"
    while :; do
        if [ -f "$directory/subedit.toml" ]; then
            return 0
        fi
        if [ -f "$directory/pyproject.toml" ] && grep -q '^\[tool\.subedit[].]' "$directory/pyproject.toml"; then
            return 0
        fi
        if [ "$directory" = / ] || [ -z "$directory" ]; then
            return 1
        fi
        directory=$(dirname "$directory")
    done
}

if ! adopts_subedit "${CLAUDE_PROJECT_DIR:-$PWD}"; then
    exit 0
fi

if ! command -v uvx >/dev/null 2>&1; then
    cat >&2 <<'MESSAGE'
subedit needs uv, so prose checks are not running.

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
