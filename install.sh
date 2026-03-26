#!/usr/bin/env bash
# Anchor CLI installer / updater
#
# - Safe to run multiple times — never deletes user data.
# - Copies the package into the venv (no editable link to source).
# - Re-run to upgrade: pulls latest code, reinstalls into venv.
set -euo pipefail

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
ANCHOR_HOME="${ANCHOR_HOME:-"$HOME/.anchors"}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ANCHOR_HOME/venv"
SHELL_DIR="$ANCHOR_HOME/shell"
COMP_DIR="$ANCHOR_HOME/completions"

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
mkdir -p "$COMP_DIR"
if $IS_UPDATE; then
    info "Data preserved: $ANCHOR_HOME/data"
else
    info "Data dir created: $ANCHOR_HOME/data"
fi

# ------------------------------------------------------------------
# 2. System dependencies
# ------------------------------------------------------------------
section "System dependencies"

MISSING=()

for cmd in python3 ssh rsync jq sshpass wg wg-quick; do
    if command -v "$cmd" &>/dev/null; then
        dim "$cmd — $(command -v "$cmd")"
    else
        MISSING+=("$cmd")
    fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    error "Missing required: ${MISSING[*]}"
    echo ""
    echo "  Install with:"
    echo "    sudo apt install ${MISSING[*]}"
    echo ""
    exit 1
fi

# ------------------------------------------------------------------
# 3. Python check (3.10+)
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
# 4. Virtual environment
# ------------------------------------------------------------------
section "Virtual environment"
if [[ -d "$VENV_DIR" ]]; then
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
# 5. Install / upgrade anchor package (non-editable)
# ------------------------------------------------------------------
section "Installing anchor CLI"
pip install --quiet --upgrade pip

# Non-editable install: copies code into venv/lib/python3.X/site-packages/
# Re-running install.sh always picks up changes from the source directory.
pip install --quiet --upgrade --force-reinstall "$SRC_DIR[vpn]"

ANC_BIN="$VENV_DIR/bin/anc"
if [[ -x "$ANC_BIN" ]]; then
    if $IS_UPDATE; then
        info "anchor-cli upgraded → $ANC_BIN"
    else
        info "anchor-cli installed → $ANC_BIN"
    fi
else
    error "anc binary not found after install — check pip output above"
    exit 1
fi

# Show installed version
ANC_VER=$("$ANC_BIN" --version 2>/dev/null || "$VENV_DIR/bin/python" -c \
    "from importlib.metadata import version; print(version('anchor-cli'))" 2>/dev/null || echo "?")
dim "Version: $ANC_VER"

# ------------------------------------------------------------------
# 6. Shell wrapper
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
# 7. Bash completion
# ------------------------------------------------------------------
section "Completions"
COMP_SRC="$SRC_DIR/completions/anc"
COMP_DST="$COMP_DIR/anc.bash"

if [[ -f "$COMP_SRC" ]]; then
    if [[ -f "$COMP_DST" ]] && diff -q "$COMP_SRC" "$COMP_DST" &>/dev/null; then
        info "Bash completion up to date"
    else
        cp "$COMP_SRC" "$COMP_DST"
        info "Bash completion installed → $COMP_DST"
    fi
else
    dim "No completion file found — skipping"
fi

# ------------------------------------------------------------------
# 8. Shell config — idempotent, only adds missing lines
# ------------------------------------------------------------------
section "Shell configuration"

add_if_missing() {
    local file="$1" marker="$2" line="$3"
    [[ -f "$file" ]] || return 0
    if grep -qF "$marker" "$file"; then
        dim "Already set in $(basename "$file"): $marker"
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
COMP_LINE="[[ -f \"$COMP_DST\" ]] && source \"$COMP_DST\""

for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    [[ -f "$rc" ]] || continue
    echo -e "  ${DIM}→ $rc${RESET}"
    add_if_missing "$rc" "$VENV_DIR/bin" "$PATH_LINE"
    add_if_missing "$rc" "ANCHOR_DIR"    "$DATA_LINE"
    add_if_missing "$rc" "anc.sh"        "$WRAP_LINE"
    add_if_missing "$rc" "anc.bash"      "$COMP_LINE"
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
echo -e "  ${DIM}Installed at:${RESET}     $ANCHOR_HOME"
echo -e "  ${DIM}Binary:${RESET}           $ANC_BIN"
echo -e "  ${DIM}Data:${RESET}             $ANCHOR_HOME/data"
echo ""
echo "  Login to server:     anc login --url http://your-server:17017"
echo "  List anchors:        anc ls"
echo "  Navigate:            anc myproject       # cd (local) or SSH session"
echo ""
