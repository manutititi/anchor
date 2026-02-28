#!/usr/bin/env bash
# Anchor CLI installer
# Creates ~/.anchors/data, sets up a Python venv, and installs the anc binary.
set -euo pipefail

ANCHOR_HOME="${ANCHOR_HOME:-"$HOME/.anchors"}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ANCHOR_HOME/venv"

GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
CYAN="\033[1;36m"
RESET="\033[0m"

info()    { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}!${RESET} $*"; }
error()   { echo -e "${RED}✗${RESET} $*" >&2; }
section() { echo -e "\n${CYAN}▶ $*${RESET}"; }

# ------------------------------------------------------------------
# 1. Directories
# ------------------------------------------------------------------
section "Creating directories"
mkdir -p "$ANCHOR_HOME/data"
info "Data dir: $ANCHOR_HOME/data"

# ------------------------------------------------------------------
# 2. Python check (3.10+)
# ------------------------------------------------------------------
section "Checking Python version"
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
    echo "Install it with: sudo apt install python3.11  (or your distro's equivalent)"
    exit 1
fi
info "Using $PYTHON_BIN ($("$PYTHON_BIN" --version))"

# ------------------------------------------------------------------
# 3. Virtual environment
# ------------------------------------------------------------------
section "Setting up virtual environment at $VENV_DIR"
if [[ ! -d "$VENV_DIR" ]]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    info "venv created"
else
    warn "venv already exists — reusing"
fi

# Activate
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ------------------------------------------------------------------
# 4. Install anchor package
# ------------------------------------------------------------------
section "Installing anchor CLI"
pip install --quiet --upgrade pip
pip install --quiet -e "$SRC_DIR"
info "anchor-cli installed → $(which anc)"

# ------------------------------------------------------------------
# 5. Shell config — add venv bin to PATH
# ------------------------------------------------------------------
section "Configuring shell"

add_if_missing() {
    local file="$1" line="$2"
    [[ -f "$file" ]] || return
    grep -Fxq "$line" "$file" && return
    echo "$line" >> "$file"
    info "Added to $file: $line"
}

PATH_LINE="export PATH=\"$VENV_DIR/bin:\$PATH\""
DATA_LINE="export ANCHOR_DIR=\"$ANCHOR_HOME/data\""

for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    add_if_missing "$rc" "$PATH_LINE"
    add_if_missing "$rc" "$DATA_LINE"
done

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
echo ""
echo -e "${GREEN}Installation complete!${RESET}"
echo ""
echo "  Reload your shell:   source ~/.bashrc"
echo "  First login:         anc login --url http://localhost:17017"
echo "  List anchors:        anc ls"
echo "  Navigate to anchor:  cd \$(anc path myproject)"
echo ""
