#!/usr/bin/env bash
# Runs subedit from PyPI through uvx, so the plugin needs nothing installed but uv.
# With "prepare", a session start, it warms the same environment in the background instead,
# because the first run installs subedit and downloads Vale, which no edit should wait on.
set -uo pipefail

SPEC='subedit[vale]>=0.5.0'
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

PAYLOAD=$(cat)

# Every shell command reaches this hook, and starting subedit costs more than a string test.
# Each shell reader in subedit-hook names a keyword its commands contain, so one with none of them is skipped.
COMMAND_KEYWORDS='commit'
case "$PAYLOAD" in
    *'"tool_name": "Bash"'* | *'"tool_name":"Bash"'*)
        matched=false
        for word in $COMMAND_KEYWORDS; do
            case "$PAYLOAD" in
                *"$word"*) matched=true ;;
            esac
        done
        if [ "$matched" = false ]; then
            exit 0
        fi
        ;;
esac

if ! command -v uvx >/dev/null 2>&1; then
    cat >&2 <<'MESSAGE'
subedit needs uv, so prose checks are not running.

    curl -LsSf https://astral.sh/uv/install.sh | sh

Install it, or remove the subedit plugin.
MESSAGE
    exit 1
fi

if [ "${1:-}" = prepare ]; then
    # Offline, the session's own check runs only once a warm environment exists, so a first session never waits.
    printf '%s' "$PAYLOAD" | uvx --offline --python "$PYTHON" --from "$SPEC" subedit-hook 2>/dev/null
    nohup uvx --python "$PYTHON" --from "$SPEC" vale --version >/dev/null 2>&1 </dev/null &
    exit 0
fi

printf '%s' "$PAYLOAD" | uvx --python "$PYTHON" --from "$SPEC" subedit-hook
