#!/bin/sh
# install.sh — one-command installer for openagentd on macOS / Linux.
#
# Usage:
#     curl -LsSf https://raw.githubusercontent.com/lthoangg/openagentd/main/install.sh | sh
#     ./install.sh                           # local checkout
#     ./install.sh --dev                     # install from GitHub main (pre-publish)
#     ./install.sh --version 0.2.0           # pin a specific PyPI version
#
# What it does:
#   1. Ensure `uv` is available (bootstrap from astral.sh/uv if missing).
#   2. Run `uv tool install openagentd` so `openagentd` lands on PATH.
#   3. Print next-step hint (`openagentd` auto-runs first-time setup).
#
# Design notes:
#   - POSIX sh, not bash — runs on Alpine, BusyBox, default macOS sh.
#   - `set -eu` aborts on any error or unset var; no `pipefail` (not POSIX).
#   - Idempotent: rerunning upgrades the existing install (uv tool install
#     replaces in place).
#   - Never runs as root — uv installs to ~/.local/bin which is per-user.

set -eu

REPO="lthoangg/openagentd"
PKG="openagentd"

SOURCE="pypi"   # pypi | git
VERSION=""      # optional pin, only meaningful for SOURCE=pypi

# ── Argument parsing ────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        --dev)
            SOURCE="git"
            shift
            ;;
        --version)
            shift
            if [ $# -eq 0 ]; then
                echo "error: --version requires an argument" >&2
                exit 2
            fi
            VERSION="$1"
            shift
            ;;
        -h|--help)
            sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "error: unknown argument: $1" >&2
            echo "run with --help for usage" >&2
            exit 2
            ;;
    esac
done

# ── Pretty output (only when stdout is a terminal) ──────────────────────────
if [ -t 1 ]; then
    BOLD="$(printf '\033[1m')"
    DIM="$(printf '\033[2m')"
    GREEN="$(printf '\033[32m')"
    RESET="$(printf '\033[0m')"
else
    BOLD=""; DIM=""; GREEN=""; RESET=""
fi

say()  { printf '%s\n' "$*"; }
step() { printf '%s==>%s %s\n' "$GREEN" "$RESET" "$*"; }
note() { printf '%s%s%s\n' "$DIM" "$*" "$RESET"; }

# ── 1. uv ──────────────────────────────────────────────────────────────────
ensure_uv() {
    if command -v uv >/dev/null 2>&1; then
        return 0
    fi

    step "Installing ${BOLD}uv${RESET} (Python package manager)"
    note "    Source: https://astral.sh/uv/install.sh"

    # Download to a temp file rather than piping to `sh` so a partial
    # download can't execute half a script.
    tmp="$(mktemp)"
    trap 'rm -f "$tmp"' EXIT
    if ! curl -LsSf https://astral.sh/uv/install.sh -o "$tmp"; then
        echo "error: failed to download uv installer" >&2
        exit 1
    fi
    sh "$tmp"
    rm -f "$tmp"
    trap - EXIT

    # uv installs to ~/.local/bin (or $XDG_BIN_HOME); add to PATH for this
    # shell so the next step works without a re-login.
    if [ -d "$HOME/.local/bin" ]; then
        PATH="$HOME/.local/bin:$PATH"
    fi
    if [ -d "${XDG_BIN_HOME:-}" ]; then
        PATH="$XDG_BIN_HOME:$PATH"
    fi
    export PATH

    if ! command -v uv >/dev/null 2>&1; then
        cat >&2 <<EOF
error: uv was installed but is not on PATH for this shell.
       Open a new terminal and re-run this script, or add
       \$HOME/.local/bin to PATH manually.
EOF
        exit 1
    fi
}

# ── 2. install openagentd via uv tool ──────────────────────────────────────
install_openagentd() {
    case "$SOURCE" in
        pypi)
            if [ -n "$VERSION" ]; then
                spec="${PKG}==${VERSION}"
            else
                spec="$PKG"
            fi
            step "Installing ${BOLD}${spec}${RESET} from PyPI"
            uv tool install --force "$spec"
            ;;
        git)
            spec="git+https://github.com/${REPO}@main"
            step "Installing ${BOLD}${PKG}${RESET} from ${REPO}@main"
            uv tool install --force "$spec"
            ;;
        *)
            echo "internal error: unknown SOURCE=$SOURCE" >&2
            exit 1
            ;;
    esac
}

# ── 3. report ──────────────────────────────────────────────────────────────
report() {
    say ""
    step "${BOLD}Installed!${RESET}"
    if command -v openagentd >/dev/null 2>&1; then
        version="$(openagentd --version 2>/dev/null || echo unknown)"
        note "    openagentd $version"
    else
        cat >&2 <<EOF
warning: 'openagentd' is not on PATH for this shell.
         Open a new terminal, or add \$HOME/.local/bin to PATH.
EOF
    fi
    say ""
    say "Next: run ${BOLD}openagentd${RESET} to launch the server."
    note "      First run walks you through provider + model selection."
    say ""
}

ensure_uv
install_openagentd
report
