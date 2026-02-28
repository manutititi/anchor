#!/usr/bin/env bash
# Anchor CLI installer / updater
#
# Safe to run multiple times — never deletes user data.
# On re-run it upgrades the package and refreshes the shell wrapper.
set -euo pipefail

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
ANCHOR_HOME="${ANCHOR_HOME:-"$HOME/.anchors"}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ANCHOR_HOME/venv"
SHELL_DIR="$ANCHOR_HOME/shell"

# ------------------------------------------------------------------
# Colors
# ------------------------------------------------------------------
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
CYAN="\033[1;36m"
DIM="\033[2m"
RESET="\033[0m"

info()    { echo -e "  ${GREEN}✓${RESET} $*"; }
warn()    { echo -e "  ${YELLOW}!${RESET} $*"; }
error()   { echo -e "  ${RED}✗${RESET} $*" >&2; }
section() { echo -e "\n${CYAN}▶ $*${RESET}"; }
dim()     { echo -e "  ${DIM}$*${RESET}"; }

# ------------------------------------------------------------------
# Detect update vs fresh install
# ------------------------------------------------------------------
IS_UPDATE=false
[[ -d "$VENV_DIR" ]] && IS_UPDATE=true

if $IS_UPDATE; then
    echo -e "\n${CYAN}Anchor CLI — update${RESET}"
    dim "Existing install: $ANCHOR_HOME"
    dim "Source:           $SRC_DIR"
else
    echo -e "\n${CYAN}Anchor CLI — fresh install${RESET}"
    dim "Install dir: $ANCHOR_HOME"
    dim "Source:      $SRC_DIR"
fi

# ------------------------------------------------------------------
# 1. Directories — data is never touched
# ------------------------------------------------------------------
section "Directories"
mkdir -p "$ANCHOR_HOME/data"
mkdir -p "$SHELL_DIR"
if $IS_UPDATE; then
    info "Data preserved: $ANCHOR_HOME/data"
else
    info "Data dir created: $ANCHOR_HOME/data"
fi

# ------------------------------------------------------------------
# 2. Python check (3.10+)
# ------------------------------------------------------------------
section "Python"
PYTHON_BIN=""
for candidate in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c 'import sys; print(sys.version_info >= (3,10))' 2>/dev/null)
        if [[ "$ver" == "True" ]]; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    error "Python 3.10+ is required but not found."
    echo "  Install: sudo apt install python3.11"
    exit 1
fi
info "Using $PYTHON_BIN ($("$PYTHON_BIN" --version))"

# ------------------------------------------------------------------
# 3. Virtual environment
# ------------------------------------------------------------------
section "Virtual environment"
if [[ -d "$VENV_DIR" ]]; then
    # Check if the venv's Python still works (breaks after system Python upgrades)
    if ! "$VENV_DIR/bin/python" -c "import sys" &>/dev/null; then
        warn "Existing venv is broken (Python was likely upgraded). Recreating…"
        rm -rf "$VENV_DIR"
        "$PYTHON_BIN" -m venv "$VENV_DIR"
        info "venv recreated"
    else
        info "venv OK: $VENV_DIR"
    fi
else
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    info "venv created: $VENV_DIR"
fi

# Activate venv for the rest of the script
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ------------------------------------------------------------------
# 4. Install / upgrade anchor package
# ------------------------------------------------------------------
section "Installing anchor CLI"
pip install --quiet --upgrade pip
pip install --quiet --upgrade -e "$SRC_DIR"

ANC_BIN=$(which anc 2>/dev/null || echo "$VENV_DIR/bin/anc")
if $IS_UPDATE; then
    info "anchor-cli upgraded → $ANC_BIN"
else
    info "anchor-cli installed → $ANC_BIN"
fi

# ------------------------------------------------------------------
# 5. Shell wrapper — always overwrite with latest version from source
# ------------------------------------------------------------------
section "Shell wrapper"
WRAPPER_SRC="$SRC_DIR/anchor/shell/anc.sh"
WRAPPER_DST="$SHELL_DIR/anc.sh"
WRAPPER_CHANGED=false

if [[ -f "$WRAPPER_SRC" ]]; then
    if [[ -f "$WRAPPER_DST" ]] && diff -q "$WRAPPER_SRC" "$WRAPPER_DST" &>/dev/null; then
        info "Shell wrapper up to date"
    else
        cp "$WRAPPER_SRC" "$WRAPPER_DST"
        WRAPPER_CHANGED=true
        if $IS_UPDATE; then
            info "Shell wrapper updated → $WRAPPER_DST"
        else
            info "Shell wrapper installed → $WRAPPER_DST"
        fi
    fi
else
    warn "anchor/shell/anc.sh not found in source — skipping"
fi

# ------------------------------------------------------------------
# 6. Shell config — idempotent, only adds missing lines
# ------------------------------------------------------------------
section "Shell configuration"

add_if_missing() {
    local file="$1" marker="$2" line="$3"
    [[ -f "$file" ]] || return 0
    if grep -qF "$marker" "$file"; then
        dim "Already set in $file"
        return 0
    fi
    echo "" >> "$file"
    echo "# anchor-cli" >> "$file"
    echo "$line" >> "$file"
    info "Added to $file"
}

PATH_LINE="export PATH=\"$VENV_DIR/bin:\$PATH\""
DATA_LINE="export ANCHOR_DIR=\"$ANCHOR_HOME/data\""
WRAP_LINE="[[ -f \"$WRAPPER_DST\" ]] && source \"$WRAPPER_DST\""

for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    [[ -f "$rc" ]] || continue
    echo -e "  ${DIM}→ $rc${RESET}"
    add_if_missing "$rc" "$VENV_DIR/bin" "$PATH_LINE"
    add_if_missing "$rc" "ANCHOR_DIR"    "$DATA_LINE"
    add_if_missing "$rc" "anc.sh"        "$WRAP_LINE"
done

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
echo ""
if $IS_UPDATE; then
    echo -e "${GREEN}Update complete!${RESET}"
else
    echo -e "${GREEN}Installation complete!${RESET}"
fi
echo ""
if $WRAPPER_CHANGED; then
    echo -e "  ${YELLOW}!${RESET} Shell wrapper changed — reload required:"
    echo -e "      ${CYAN}source ~/.bashrc${RESET}   (or open a new terminal)"
else
    echo "  Reload your shell:   source ~/.bashrc"
fi
echo ""
echo "  Login to server:     anc login --url http://localhost:17017"
echo "  List anchors:        anc ls"
echo "  Navigate:            anc myproject       # cd (local) or SSH session"
echo ""
