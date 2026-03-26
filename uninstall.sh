#!/usr/bin/env bash
set -euo pipefail

ANCHOR_HOME="${ANCHOR_HOME:-"$HOME/.anchors"}"
KEEP_DATA=false

RESET="\033[0m"
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
CYAN="\033[1;36m"
DIM="\033[2m"

info()    { echo -e "  ${GREEN}✓${RESET} $*"; }
warn()    { echo -e "  ${YELLOW}!${RESET} $*"; }
section() { echo -e "\n${CYAN}▶ $*${RESET}"; }
dim()     { echo -e "  ${DIM}$*${RESET}"; }

for arg in "$@"; do
  case "$arg" in
    --keep-data) KEEP_DATA=true ;;
    *) echo -e "${RED}Unknown option: $arg${RESET}"; exit 1 ;;
  esac
done

echo -e "\n${CYAN}Anchor CLI — uninstall${RESET}"
dim "Install dir: $ANCHOR_HOME"

# ------------------------------------------------------------------
# 1. Remove installation directory (optionally preserve data)
# ------------------------------------------------------------------
section "Removing files"

if [[ -d "$ANCHOR_HOME" ]]; then
  if $KEEP_DATA; then
    # Remove everything except data/
    for entry in "$ANCHOR_HOME"/*/; do
      name="$(basename "$entry")"
      if [[ "$name" != "data" ]]; then
        rm -rf "$entry"
        dim "Removed: $entry"
      fi
    done
    # Remove any top-level files (not dirs)
    find "$ANCHOR_HOME" -maxdepth 1 -type f -delete
    info "Preserved data: $ANCHOR_HOME/data"
  else
    rm -rf "$ANCHOR_HOME"
    info "Removed: $ANCHOR_HOME"
  fi
else
  warn "Directory not found: $ANCHOR_HOME"
fi

# ------------------------------------------------------------------
# 2. Clean shell config files
# ------------------------------------------------------------------
section "Cleaning shell configuration"

clean_shell_config() {
  local config="$1"
  [[ -f "$config" ]] || return 0

  dim "Cleaning $(basename "$config")..."

  # Lines written by current install.sh:
  #   export PATH="$VENV_DIR/bin:$PATH"      (marker: .anchors/venv/bin)
  #   export ANCHOR_DIR="$ANCHOR_HOME/data"  (marker: ANCHOR_DIR)
  #   [[ -f "...anc.sh" ]] && source "..."   (marker: anc.sh)
  #   [[ -f "...anc.bash" ]] && source "..."  (marker: anc.bash)
  #   # anchor-cli                            (section comment)
  sed -i '/\.anchors\/venv\/bin/d'     "$config"
  sed -i '/export ANCHOR_DIR=/d'       "$config"
  sed -i '/anc\.sh/d'                  "$config"
  sed -i '/anc\.bash/d'                "$config"
  sed -i '/^# anchor-cli$/d'           "$config"

  # Legacy patterns from older installs:
  sed -i '/export ANCHOR_HOME=.*\.anchors/d'         "$config"
  sed -i '/export ANCHOR_ROOT=.*\.anchors/d'         "$config"
  sed -i '/for f in.*ANCHOR_HOME.*functions/d'       "$config"
  sed -i '/source.*ANCHOR_HOME.*completions\/anc"/d' "$config"
  sed -i '/PATH=.*ANCHOR_HOME.*core.*PATH/d'         "$config"
  sed -i '/source.*\.anchors.*venv.*activate/d'      "$config"

  info "Cleaned: $config"
}

clean_shell_config "$HOME/.bashrc"
clean_shell_config "$HOME/.zshrc"

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
echo ""
echo -e "${GREEN}Uninstallation complete.${RESET}"
if $KEEP_DATA; then
  echo -e "  ${YELLOW}!${RESET} Data preserved at: $ANCHOR_HOME/data"
fi
echo -e "  Reload your shell:   ${CYAN}source ~/.bashrc${RESET}"
echo ""
