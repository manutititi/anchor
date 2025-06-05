#!/usr/bin/env bash
set -e

ANCHOR_HOME="$HOME/.anchors"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"
CYAN="\033[1;36m"

echo -e "📦 Installing Anchor system to: ${GREEN}$ANCHOR_HOME${RESET}"


# jq
if ! command -v jq >/dev/null 2>&1; then
  echo -e "${YELLOW}🔧 'jq' not found. Installing...${RESET}"
  if command -v sudo >/dev/null && command -v apt >/dev/null; then
    sudo apt update && sudo apt install -y jq
  elif command -v sudo >/dev/null && command -v pacman >/dev/null; then
    sudo pacman -Sy jq
  elif command -v brew >/dev/null; then
    brew install jq
  else
    echo -e "${RED}❌ Install jq manually${RESET}"
    exit 1
  fi
else
  echo -e "${GREEN}✅ 'jq' already installed.${RESET}"
fi

mkdir -p "$ANCHOR_HOME"
mkdir -p "$ANCHOR_HOME/functions"
mkdir -p "$ANCHOR_HOME/completions"
mkdir -p "$ANCHOR_HOME/data"
mkdir -p "$ANCHOR_HOME/scripts"
mkdir -p "$ANCHOR_HOME/server"
mkdir -p "$ANCHOR_HOME/core"

cp -r "$SRC_DIR/functions/"*.sh "$ANCHOR_HOME/functions/"
cp -r "$SRC_DIR/completions/"* "$ANCHOR_HOME/completions/"
cp -r "$SRC_DIR/scripts/"* "$ANCHOR_HOME/scripts/" 2>/dev/null || true
cp -r "$SRC_DIR/server/"* "$ANCHOR_HOME/server/" 2>/dev/null || true
cp -r "$SRC_DIR/core" "$ANCHOR_HOME/"

if compgen -G "$SRC_DIR/data/*.json" > /dev/null; then
  cp "$SRC_DIR/data/"*.json "$ANCHOR_HOME/data/"
  echo -e "${GREEN}✅ Copied anchor examples to ~/.anchors/data/${RESET}"
fi

SHELL_CONFIGS=("$HOME/.bashrc" "$HOME/.zshrc")

add_if_missing() {
  local file="$1"
  local line="$2"
  grep -Fxq "$line" "$file" || echo "$line" >> "$file"
}

for CONFIG in "${SHELL_CONFIGS[@]}"; do
  if [[ -f "$CONFIG" ]]; then
    add_if_missing "$CONFIG" 'export ANCHOR_HOME="$HOME/.anchors"'
    add_if_missing "$CONFIG" 'export ANCHOR_DIR="$HOME/.anchors/data"'
    add_if_missing "$CONFIG" 'export PATH="$ANCHOR_HOME/core:$PATH"'
    add_if_missing "$CONFIG" 'for f in "$ANCHOR_HOME/functions/"*.sh; do source "$f"; done'
    add_if_missing "$CONFIG" '[[ -f "$ANCHOR_HOME/completions/anc" ]] && source "$ANCHOR_HOME/completions/anc"'
    echo -e "${GREEN}✅ Updated $CONFIG${RESET}"
  fi
done

# Python virtual environment setup
echo -e "\n🐍 Setting up Python virtual environment..."

VENV_DIR="$ANCHOR_HOME/venv"
REQ_FILE="$SRC_DIR/requirements.txt"

# Generate default requirements.txt if missing
if [[ ! -f "$REQ_FILE" ]]; then
  cat > "$REQ_FILE" <<EOF
ldap3
PyYAML
requests
ldif
jinja2
simpleeval
EOF
  echo -e "${YELLOW}📦 Default requirements.txt created${RESET}"
fi

python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip >/dev/null
echo -e "${CYAN}📥 Installing Python dependencies...${RESET}"
pip install -r "$REQ_FILE"

echo -e "${GREEN}✅ Python environment ready in $VENV_DIR${RESET}"

echo -e "\n🎉 ${GREEN}Installation complete!${RESET}"
echo "🔁 Reload your shell or run: source ~/.bashrc"
echo -e "📦 Example anchor installed: ${CYAN}anc.json${RESET}"
echo -e "🚀 Try: ${GREEN}anc ls${RESET}  then ${CYAN}anc anc${RESET} to jump into it."

