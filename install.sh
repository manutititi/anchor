#!/usr/bin/env bash

set -e

ANCHOR_HOME="$HOME/.anchors"
SRC_DIR="$(pwd)"

GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

echo -e "📦 Installing Anchor system to: ${GREEN}$ANCHOR_HOME${RESET}"

# === INSTALAR DEPENDENCIAS === #

# Verificar yq
if ! command -v yq >/dev/null 2>&1; then
  echo -e "${YELLOW}🔧 'yq' not found. Installing via snap...${RESET}"
  if command -v sudo >/dev/null && command -v snap >/dev/null; then
    sudo snap install yq
    echo -e "${GREEN}✅ 'yq' installed via snap.${RESET}"
  else
    echo -e "${RED}❌ Could not install 'yq'. Install manually: https://github.com/mikefarah/yq${RESET}"
    exit 1
  fi
else
  echo -e "${GREEN}✅ 'yq' already installed.${RESET}"
fi

# Verificar jq
if ! command -v jq >/dev/null 2>&1; then
  echo -e "${YELLOW}🔧 'jq' not found. Attempting install...${RESET}"
  if command -v sudo >/dev/null && command -v apt >/dev/null; then
    sudo apt update && sudo apt install -y jq
  elif command -v sudo >/dev/null && command -v pacman >/dev/null; then
    sudo pacman -Sy jq
  elif command -v brew >/dev/null; then
    brew install jq
  else
    echo -e "${RED}❌ Could not install 'jq'. Please install it manually.${RESET}"
    exit 1
  fi
else
  echo -e "${GREEN}✅ 'jq' already installed.${RESET}"
fi

# Verificar tree (opcional)
if ! command -v tree >/dev/null 2>&1; then
  echo -e "${YELLOW}⚠️  'tree' not found. Optional but recommended (used by 'anc <anchor> tree')${RESET}"
  echo -e "${YELLOW}   ➤ You can install it with:${RESET} sudo apt install tree ${DIM}(or brew/pacman)${RESET}"
else
  echo -e "${GREEN}✅ 'tree' installed.${RESET}"
fi

# === COPIAR ARCHIVOS === #

mkdir -p "$ANCHOR_HOME/functions"
mkdir -p "$ANCHOR_HOME/completions"
mkdir -p "$ANCHOR_HOME/data"

cp "$SRC_DIR/functions/"*.sh "$ANCHOR_HOME/functions/"
cp "$SRC_DIR/completions/anc" "$ANCHOR_HOME/completions/anc"

# === MODIFICAR CONFIGURACIÓN DEL SHELL === #

SHELL_CONFIGS=("$HOME/.bashrc" "$HOME/.zshrc")

add_if_missing() {
  local file="$1"
  local line="$2"
  grep -Fxq "$line" "$file" || echo "$line" >> "$file"
}

for CONFIG in "${SHELL_CONFIGS[@]}"; do
  if [[ -f "$CONFIG" ]]; then
    add_if_missing "$CONFIG" 'export ANCHOR_HOME="$HOME/.anchors"'
    add_if_missing "$CONFIG" 'export ANCHOR_DIR="$ANCHOR_HOME/data"'
    add_if_missing "$CONFIG" 'for f in "$ANCHOR_HOME/functions/"*.sh; do source "$f"; done'
    add_if_missing "$CONFIG" '[[ -f "$ANCHOR_HOME/completions/anc" ]] && source "$ANCHOR_HOME/completions/anc"'
    echo -e "${GREEN}✅ Updated $CONFIG${RESET}"
  fi
done

# === MENSAJE FINAL === #

echo -e "\n🎉 ${GREEN}Installation complete!${RESET}"
echo "🔁 Please reload your shell or run: source ~/.bashrc or ~/.zshrc"
echo "🚀 Try: anc set test && anc ls"

